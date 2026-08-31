#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Durable ledger for the admin storage-disk path->path migration.

Two RethinkDB tables, modelled on ``models/storage_pool.py``:

* ``storage_migration``      — one row per migration *job* (the aggregate).
* ``storage_migration_item`` — one row per *disk* (the resumable unit).

RQ stays the executor; these tables are the source of truth so the job has
aggregate totals, survives restarts and is resumable. Because the
``stream:task-results`` bridge is at-least-once, every ledger write is an
idempotent upsert keyed by the item ``id`` and every aggregate is computed as
``COUNT(items WHERE state=X)`` — never a per-event increment.

Both tables MUST be registered in ``engine/engine/initdb/populate.py`` or
``check_integrity`` drops them on every engine startup.
"""

from enum import StrEnum
from time import time
from typing import Iterable, Literal
from uuid import uuid4

from isardvdi_common.connections.rethink_custom_base_factory import RethinkCustomBase
from pydantic import BaseModel, Field
from rethinkdb import r


# --------------------------------------------------------------------------- #
# Enums
# --------------------------------------------------------------------------- #
class MigrationStatus(StrEnum):
    """Lifecycle of a migration *job*."""

    DRAFT = "draft"
    PLANNED = "planned"
    RUNNING = "running"
    PAUSED = "paused"
    WINDOW_CLOSED = "window_closed"
    FINISHING_TREE = "finishing_tree"
    #: recurring job between occurrences — idle, NON-TERMINAL, awaiting the next
    #: scheduled occurrence (window opens on a selected weekday) to re-scan and
    #: drain. Only an admin Cancel ends a recurring job; it never self-completes.
    #: Set only by the reconciler, never directly by an admin action.
    SCHEDULED = "scheduled"
    #: this occurrence's byte budget is spent -- idle, NON-TERMINAL, and still
    #: DRIVABLE, which is what makes the two recoveries work: a recurring job
    #: resumes by itself when its next occurrence resets the spend, and a
    #: one-shot resumes on the next tick once an admin raises the budget.
    #: Mirrors WINDOW_CLOSED: stopped on purpose, not broken.
    BUDGET_REACHED = "budget_reached"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class MigrationItemState(StrEnum):
    """Per-disk saga state.

    The happy path advances strictly in ``MIGRATION_ITEM_STATE_ORDER``. A disk
    enters ``moving`` only once its parent item is ``released`` (top-to-bottom).
    ``skipped`` (e.g. a running desktop the admin chose not to force-stop) and
    ``failed`` are off-path.
    """

    PENDING = "pending"
    PREFLIGHT_OK = "preflight_ok"
    MOVING = "moving"
    MOVED = "moved"
    REBASED = "rebased"
    DB_UPDATED = "db_updated"
    RELEASED = "released"
    FAILED = "failed"
    SKIPPED = "skipped"
    #: a disk that FAILED on ``quarantine_after`` consecutive occurrences under
    #: the ``retry_quarantine`` policy — terminal, never re-armed on later
    #: re-scans, surfaced in the audit log.
    QUARANTINED = "quarantined"


class MigrationItemKind(StrEnum):
    TEMPLATE = "template"
    DESKTOP = "desktop"
    MEDIA = "media"


#: Canonical happy-path order. Index in this list == saga progress.
MIGRATION_ITEM_STATE_ORDER = [
    MigrationItemState.PENDING,
    MigrationItemState.PREFLIGHT_OK,
    MigrationItemState.MOVING,
    MigrationItemState.MOVED,
    MigrationItemState.REBASED,
    MigrationItemState.DB_UPDATED,
    MigrationItemState.RELEASED,
]

#: States that need no further work. ``failed`` is deliberately NOT here: a
#: failed disk needs attention, so resume/aggregation treat it as unfinished.
#: ``quarantined`` IS here: it is a settled off-path terminal (no more retries).
DONE_ITEM_STATES = {
    MigrationItemState.RELEASED,
    MigrationItemState.SKIPPED,
    MigrationItemState.QUARANTINED,
}


# --------------------------------------------------------------------------- #
# Pure helpers (no DB) — unit tested
# --------------------------------------------------------------------------- #
def _state_of(item) -> str:
    """Read the ``state`` of an item given as dict or object, as a plain str."""
    state = item["state"] if isinstance(item, dict) else getattr(item, "state")
    return str(state)


def _size_of(item) -> int:
    size = (
        item["size_bytes"] if isinstance(item, dict) else getattr(item, "size_bytes", 0)
    )
    return int(size or 0)


def item_is_done(state) -> bool:
    """True for states that need no further saga work (released / skipped)."""
    return state in DONE_ITEM_STATES


def compute_state_counts(items: Iterable) -> dict:
    """``{state: count}`` over items (dicts or objects). Enum states normalised
    to their string value so the result is plain JSON for the ledger."""
    counts: dict = {}
    for it in items:
        s = _state_of(it)
        counts[s] = counts.get(s, 0) + 1
    return counts


def compute_bytes_done(items: Iterable) -> int:
    """Bytes physically moved AND committed: the sum of ``size_bytes`` over
    items in ``released`` (a disk is only counted once its whole per-disk saga
    has committed, never mid-flight)."""
    return sum(
        _size_of(it) for it in items if _state_of(it) == MigrationItemState.RELEASED
    )


def build_totals(current: dict, items: list) -> dict:
    """Re-derive the live aggregate from item states (pure, never incremental).

    The static plan fields in ``current`` (trees / desktops / bytes_total / ...)
    are preserved; the dynamic ones are recomputed. ``done`` is the count of
    disks past the saga (released/skipped) — the UI progress field (ledger-1).
    """
    if not isinstance(current, dict):
        current = {}
    return {
        **current,
        "items_total": len(items),
        "state_counts": compute_state_counts(items),
        "bytes_done": compute_bytes_done(items),
        "done": sum(1 for it in items if item_is_done(_state_of(it))),
    }


# --------------------------------------------------------------------------- #
# Pydantic models (defaults + serialisation) — used by the plan builder/service
# to construct well-formed rows; unit tested for defaults/serialisation.
# --------------------------------------------------------------------------- #
class MigrationWindow(BaseModel):
    start: str | None = None  # "HH:MM"
    end: str | None = None  # "HH:MM"
    tz: str = "UTC"
    #: ISO-ish weekdays the window is active, Mon=0 … Sun=6 (datetime.weekday()).
    #: Empty == every day (backward compatible with the pre-schedule behaviour).
    days: list[int] = Field(default_factory=list)


class MigrationSelection(BaseModel):
    """What the job migrates and where to."""

    kind: Literal["pool", "path", "category"] = "pool"
    src_pool_id: str | None = None
    dst_pool_id: str | None = None
    category_id: str | None = None
    path_prefix: str | None = None
    #: explicit root storage ids when the admin selects specific trees
    tree_ids: list[str] = Field(default_factory=list)


class MigrationConfig(BaseModel):
    """Admin-set, per-job knobs."""

    # 0 == unlimited (rsync --bwlimit, KB/s); a negative value would emit
    # --bwlimit=-N and fail every move.
    bwlimit_kbs: int = Field(default=0, ge=0)
    # concurrent independent trees; an unbounded value defeats the throttle and
    # mass-flips storage rows to maintenance.
    parallelism: int = Field(default=1, ge=1, le=64)
    window: MigrationWindow | None = None
    verify: bool = True  # qemu_img_check after move/rebase
    force_stop_desktops: bool = False
    #: per-job schedule toggle. False == one-shot (runs on its scheduled
    #: days/window until the current disks are migrated, then terminal
    #: ``completed``). True == recurring: at each occurrence re-scan the
    #: selection, drain newly-matching disks, and return to ``scheduled`` — never
    #: self-terminates (only Cancel ends it). A recurring job requires a window.
    recurring: bool = False
    #: when a recurring job re-scans (all via insert-new-only, never disturbing
    #: in-flight): ``edge`` only at the occurrence edge; ``edge_on_drain`` also
    #: once the current batch has drained and the window is still open;
    #: ``continuous`` every tick while the window is open.
    rescan_cadence: Literal["edge", "edge_on_drain", "continuous"] = "edge_on_drain"
    #: how a disk failure is handled: ``retry_quarantine`` keeps the job alive and
    #: quarantines a disk that fails ``quarantine_after`` consecutive occurrences;
    #: ``pause`` moves the job to paused on any failure for admin attention;
    #: ``retry_forever`` keeps retrying every occurrence, never quarantining.
    failure_policy: Literal["retry_quarantine", "pause", "retry_forever"] = (
        "retry_quarantine"
    )
    #: consecutive-occurrence failure budget before a disk is quarantined (used
    #: only by ``retry_quarantine``).
    quarantine_after: int = Field(default=3, ge=1)


class MigrationTotals(BaseModel):
    trees: int = 0
    derivative_templates: int = 0
    desktops: int = 0
    media: int = 0
    items_total: int = 0
    bytes_total: int = 0
    bytes_done: int = 0
    #: COUNT(items WHERE state=X) — recomputed, never incremented
    state_counts: dict = Field(default_factory=dict)


class StorageMigrationModel(BaseModel):
    """A migration job (the aggregate ledger row)."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    status: MigrationStatus = MigrationStatus.DRAFT
    selection: MigrationSelection = Field(default_factory=MigrationSelection)
    config: MigrationConfig = Field(default_factory=MigrationConfig)
    totals: MigrationTotals = Field(default_factory=MigrationTotals)
    #: EWMA MB/s keyed on "<src_pool>:<dst_pool>" (P2 window/ETA)
    throughput_ewma: dict = Field(default_factory=dict)
    current_window: dict | None = None
    #: occurrence key (start-date string, e.g. "2026-07-01") of the most recent
    #: re-scan; drives fresh-occurrence detection for a recurring job. None until
    #: the first occurrence has been scanned. Runtime state — never in config.
    last_occurrence: str | None = None
    logs: list = Field(default_factory=list)
    created_by: str | None = None
    created_at: float | None = None
    updated_at: float | None = None


class StorageMigrationItemModel(BaseModel):
    """A single disk = the resumable unit of work."""

    id: str = Field(default_factory=lambda: str(uuid4()))
    migration_id: str
    storage_id: str
    tree_id: str  # root storage id of this disk's tree
    topo_index: int = 0  # BFS topo order within the tree (parents first)
    kind: MigrationItemKind = MigrationItemKind.DESKTOP
    src_path: str | None = None
    dst_path: str | None = None
    dst_dir: str | None = None
    size_bytes: int = 0  # fresh `qemu-img info -U` probe at plan time
    bytes_done: int = 0
    parent_storage_id: str | None = None
    parent_dst_dir: str | None = None
    parent_dst_path: str | None = None  # rebase target (parent's NEW path)
    state: MigrationItemState = MigrationItemState.PENDING
    move_task_id: str | None = None
    rebase_task_id: str | None = None
    #: pre-release destination-verify task (the unconditional gate that proves the
    #: destination is sound before the source is move_deleted)
    verify_task_id: str | None = None
    #: count of orphan-RESUME re-enqueues (a task whose worker died); bounds the
    #: resume so a perpetually-abandoned task terminalizes instead of looping
    abandon_restarts: int = 0
    #: storage row status BEFORE we set it to maintenance, so release/failure
    #: restore the ORIGINAL status (e.g. "recycled") instead of hardcoding
    #: "ready". None == we never put this disk into maintenance.
    storage_orig_status: str | None = None
    attempts: int = 0
    #: consecutive occurrences (recurring) in which this disk ended ``failed``;
    #: drives the ``retry_quarantine`` budget. Reset by a non-failed occurrence.
    occurrence_failures: int = 0
    #: append-only per-occurrence AUDIT trail for the downloadable log: one record
    #: per terminal outcome (moved_ok | failed | skipped | quarantined | in_place),
    #: annotated by occurrence so recurring history is preserved across re-arms.
    audit: list = Field(default_factory=list)
    checkpoints: list = Field(default_factory=list)
    error: str | None = None
    #: domain whose autostart we suppressed (for crash-safe re-activation)
    domain_id: str | None = None
    #: server_autostart value before we deactivated it (None == not touched)
    autostart_was_on: bool | None = None
    # The source file is still on disk and no row points at it any more: its
    # move_delete could not be placed, and nothing will retry it.
    source_retained: bool = False
    source_retained_path: str | None = None


# --------------------------------------------------------------------------- #
# RethinkCustomBase models
# --------------------------------------------------------------------------- #
class StorageMigrationItem(RethinkCustomBase):
    """Disk-level ledger row. ``_rdb_table_schema`` is left as the lax blank
    model (like ``StoragePool``) so single-field ``__setattr__`` writes work."""

    _rdb_table = "storage_migration_item"

    @classmethod
    def by_migration(cls, migration_id):
        """All items of a job as model instances."""
        return cls.get_index([migration_id], "migration_id")

    @classmethod
    def dicts_by_migration(cls, migration_id):
        """All items of a job as raw dicts (cheap — one query, no per-row get)."""
        with cls._rdb_context():
            return list(
                r.table(cls._rdb_table)
                .get_all(migration_id, index="migration_id")
                .run(cls._rdb_connection)
            )

    @classmethod
    def dicts_by_tree(cls, migration_id, tree_id):
        with cls._rdb_context():
            return list(
                r.table(cls._rdb_table)
                .get_all([migration_id, tree_id], index="migration_tree")
                .run(cls._rdb_connection)
            )

    @classmethod
    def state_counts(cls, migration_id):
        """``{state: count}`` computed in the DB (aggregate from item states)."""
        with cls._rdb_context():
            grouped = (
                r.table(cls._rdb_table)
                .get_all(migration_id, index="migration_id")
                .group("state")
                .count()
                .run(cls._rdb_connection)
            )
        return {str(k): v for k, v in grouped.items()}

    @classmethod
    def upsert(cls, data: dict):
        """Idempotent create/update keyed by ``id`` (at-least-once safe)."""
        return cls.insert_document(data, conflict="update")

    def advance(self, state, **fields):
        """Persist a new state (+ optional fields) and append a checkpoint.

        Idempotent: re-advancing to the same state just re-stamps. The
        checkpoint append uses a server-side update so concurrent field writes
        don't clobber the list.
        """
        state = str(state)
        update = {"state": state, **fields}
        with self._rdb_context():
            r.table(self._rdb_table).get(self.id).update(
                lambda row: r.expr(update).merge(
                    {
                        "checkpoints": row["checkpoints"]
                        .default([])
                        .append({"state": state, "at": time()})
                    }
                )
            ).run(self._rdb_connection)
        self._update_cache(**update)
        return update

    @classmethod
    def claim(cls, item_id, *, when: dict, set_fields: dict) -> bool:
        """Atomic conditional ledger claim (RethinkDB per-document atomicity).

        Apply ``set_fields`` to the item IFF every field named in ``when``
        currently equals its given value (a missing field matches ``None``).
        Returns ``True`` iff THIS call is the one that applied the change, so two
        concurrent drivers racing to (re-)enqueue the same disk's storage task
        yield exactly ONE winner — making single-writer-per-disk a property of the
        LEDGER, not of who happens to call the reconciler. ``set_fields`` MUST
        change at least one field away from its ``when`` value (the callers use a
        state transition or a unique fence), so a genuine winner always reports
        ``replaced`` and the loser reports ``unchanged``.

        A single-document ``update`` is atomic in RethinkDB, so the two racing
        updates are serialized: the first flips the guarded field(s) and the
        second's ``when`` predicate no longer holds, yielding ``{}`` (no-op).
        """
        # An empty ``when`` makes ``r.and_()`` evaluate to true, degrading the CAS
        # to an unconditional write (every concurrent caller "wins") -- never a
        # legitimate claim. Fail loudly instead of silently disabling the guard.
        if not when:
            raise ValueError("claim() requires a non-empty `when` predicate")
        with cls._rdb_context():
            res = (
                r.table(cls._rdb_table)
                .get(item_id)
                .update(
                    lambda row: r.branch(
                        r.and_(*[row[f].default(None).eq(v) for f, v in when.items()]),
                        set_fields,
                        {},
                    )
                )
                .run(cls._rdb_connection)
            )
        return bool(res.get("replaced", 0))

    @classmethod
    def incr(cls, item_id, field, by: int = 1):
        """Atomically increment an integer ``field`` and return its NEW value.

        Server-side ``row[field].default(0).add(by)`` so a lost read-modify-write
        can never defeat a bound (e.g. ``abandon_restarts`` vs
        ``MAX_ABANDON_RESTARTS``). Returns the post-increment value, or ``None`` if
        the item is gone.
        """
        with cls._rdb_context():
            res = (
                r.table(cls._rdb_table)
                .get(item_id)
                .update(
                    lambda row: {field: row[field].default(0).add(by)},
                    return_changes=True,
                )
                .run(cls._rdb_connection)
            )
        try:
            return res["changes"][0]["new_val"][field]
        except (KeyError, IndexError, TypeError):
            return None


class StorageMigration(RethinkCustomBase):
    """Job-level ledger row."""

    _rdb_table = "storage_migration"

    @classmethod
    def ids_by_status(cls, status):
        """Ids of migrations in a given status (via the ``status`` index). Used
        by the scheduler tick to find the jobs it must drive."""
        with cls._rdb_context():
            return list(
                r.table(cls._rdb_table)
                .get_all(status, index="status")["id"]
                .run(cls._rdb_connection)
            )

    def item_dicts(self):
        return StorageMigrationItem.dicts_by_migration(self.id)

    def items(self):
        return StorageMigrationItem.by_migration(self.id)

    def recompute_totals(self):
        """Re-derive the live aggregate from item states (never incremental).

        Returns the new ``totals`` dict and persists it.
        """
        items = self.item_dicts()
        totals = build_totals(self.totals or {}, items)
        # ledger-0: replace the WHOLE totals via r.literal. A plain update (what
        # __setattr__ does) deep-merges, so an emptied state_counts key (e.g.
        # "pending" once a job completes) would keep its stale count forever and
        # list/get/action/config would report phantom pending/moving disks.
        with self._rdb_context():
            r.table(self._rdb_table).get(self.id).update(
                {"totals": r.literal(totals)}
            ).run(self._rdb_connection)
        self._update_cache(totals=totals)
        return totals
