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

"""Executor for the per-disk storage-migration saga (the reconciler).

A crash-safe, idempotent reconciliation loop. Each :meth:`MigrationRunner.tick`
advances every tree by at most one step, driven by the pure
:func:`isardvdi_common.lib.storage.migration.tree_next` decision and the live
RQ task statuses. Because the ledger (state + task ids) is the source of truth
and is re-read every tick, a crash simply resumes from the last persisted
boundary.

Physical disk ops (``move`` rsync, ``rebase``, ``move_delete``) run on the
isard-storage RQ worker; this runner only enqueues them, observes their RQ
status, and performs the DB-write / release half — so it needs NO disks mounted
and is safe to host in isard-scheduler (the singleton orchestrator).
"""

import logging
from datetime import datetime, timezone
from os.path import dirname
from time import time

try:  # py3.9+ stdlib; always present on our 3.13 images
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

import redis
from isardvdi_common.connections.redis_urls import rq_url
from isardvdi_common.helpers.desktop_events import DesktopEvents
from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.models.domain import Domain
from isardvdi_common.models.storage import Storage, get_queue_from_storage_pools
from isardvdi_common.models.storage_migration import (
    MigrationItemState,
    MigrationStatus,
    StorageMigration,
    StorageMigrationItem,
)
from isardvdi_common.models.storage_pool import StoragePool
from isardvdi_common.models.task import Task

log = logging.getLogger(__name__)

DEFAULT_PRIORITY = "default"
RSYNC_TIMEOUT = 43200  # 12h, matching Storage.rsync
#: stream the change-handler consumes; XADD a migration progress event here so
#: the change-handler emits the aggregate storage:migration SocketIO event.
TASK_RESULTS_STREAM = "stream:task-results"
TASK_RESULTS_STREAM_MAXLEN = 10000
#: how many ticks a force-stopped desktop may stay un-Stopped before the disk
#: is failed — surfaces a stuck force-stop instead of looping forever (the
#: study's "bound the desktops_not_stopped retry; no silent pass").
QUIESCE_MAX_ATTEMPTS = 60


def job_status(task_id):
    """RQ status of a task id, or ``None`` if absent."""
    if not task_id:
        return None
    try:
        if not Task.exists(task_id):
            return None
        return Task(task_id).job_status
    except Exception:
        return None


class MigrationRunner:
    def __init__(self, migration_id, *, job_status_fn=job_status):
        self.migration_id = migration_id
        self.migration = StorageMigration(migration_id)
        selection = self.migration.selection or {}
        self.dst_pool = StoragePool(selection["dst_pool_id"])
        self.config = self.migration.config or {}
        self.user_id = self.migration.created_by or "admin"
        self.job_status_fn = job_status_fn

    # -- helpers ----------------------------------------------------------- #
    def _items(self):
        return StorageMigrationItem.dicts_by_migration(self.migration_id)

    def _set(self, item, **fields):
        """Idempotent ledger write keyed by item id (at-least-once safe)."""
        StorageMigrationItem.update_document(item["id"], fields, validate=False)
        item.update(fields)

    def _move_queue(self, src_path):
        src_pool = self._pool_of(src_path)
        return f"storage.{get_queue_from_storage_pools(src_pool, self.dst_pool)}.{DEFAULT_PRIORITY}"

    def _pool_queue(self, path):
        return f"storage.{self._pool_of(path).id}.{DEFAULT_PRIORITY}"

    def _pool_of(self, path):
        pools = StoragePool.get_by_path(dirname(path))
        return pools[0] if pools else self.dst_pool

    def _enqueue(self, task, queue, kwargs, timeout=None):
        job_kwargs = {"kwargs": kwargs}
        if timeout:
            job_kwargs["timeout"] = timeout
        return Task(
            task=task,
            queue=queue,
            user_id=self.user_id,
            job_kwargs=job_kwargs,
        ).id

    # -- autostart guard / quiesce ----------------------------------------- #
    def _domains(self, storage_id):
        try:
            return Domain.get_with_storage(Storage(storage_id))
        except Exception:
            log.exception("migration: could not read domains of %s", storage_id)
            return []

    def prepare(self):
        """Deactivate autostart for EVERY desktop in the migration up front
        (the mandatory livelock guard — the ~10s autostart loop must never beat
        the move window). The prior ``server_autostart`` of each domain is
        recorded in the ledger so re-activation is crash-safe (driven from the
        ledger on resume).

        Crash-safe suppression (qcow-2): the deactivation set is re-derived from
        the FULL ledger every prepare (already-recorded items included) and
        applied BEFORE the records are persisted, so a crash (or a swallowed
        batch error) between recording and deactivating can never leave a domain
        recorded-but-not-suppressed — the next prepare re-deactivates it
        (deactivate_autostart is idempotent).
        """
        writes, to_deactivate = mig.plan_autostart_deactivation(
            self._items(), self._domains
        )
        if to_deactivate:
            DesktopEvents.deactivate_autostart(to_deactivate)
        for item, records in writes:
            self._set(item, autostart_domains=records)

    def reactivate(self):
        """Re-activate autostart for the domains we turned off (those recorded
        ``was_on``). Crash-safe + idempotent: re-derived from the ledger."""
        to_activate = []
        for item in self._items():
            for rec in item.get("autostart_domains") or []:
                if rec.get("was_on"):
                    to_activate.append(rec["id"])
        if to_activate:
            DesktopEvents.activate_autostart(to_activate)

    # -- window / EWMA-ETA admission (P2.2) -------------------------------- #
    def _now(self, tz):
        if ZoneInfo is not None:
            try:
                return datetime.now(ZoneInfo(tz))
            except Exception:
                pass
        return datetime.now(timezone.utc)

    def _window_state(self):
        """Return ``(has_window, is_open, remaining_seconds)`` for the job's
        configured maintenance window (no window -> open, unbounded)."""
        window = (self.config or {}).get("window") or {}
        start = mig.parse_hhmm(window.get("start"))
        end = mig.parse_hhmm(window.get("end"))
        if start is None or end is None:
            return False, True, float("inf")
        now = self._now(window.get("tz") or "UTC")
        now_min = now.hour * 60 + now.minute
        return (
            True,
            mig.window_is_open(start, end, now_min),
            mig.window_remaining_seconds(start, end, now_min),
        )

    def _tree_key(self, tree_items):
        """EWMA throughput key for a tree: ``<src_pool>:<dst_pool>`` using the
        tree root's source pool."""
        root = min(tree_items, key=lambda it: it.get("topo_index", 0))
        return f"{self._pool_of(root['src_path']).id}:{self.dst_pool.id}"

    def _admit_tree(self, tree_items, win_open, remaining_s):
        """Whether a not-yet-started tree may begin now (window + ETA)."""
        if not win_open:
            return False
        mbps = (self.migration.throughput_ewma or {}).get(self._tree_key(tree_items))
        remaining_bytes = sum(int(it.get("size_bytes") or 0) for it in tree_items)
        tree_eta = mig.tree_eta_seconds(remaining_bytes, mbps)
        max_disk = max((int(it.get("size_bytes") or 0) for it in tree_items), default=0)
        max_disk_eta = mig.tree_eta_seconds(max_disk, mbps)
        return mig.tree_admitted(tree_eta, max_disk_eta, remaining_s, RSYNC_TIMEOUT)

    def _record_throughput(self, item):
        """Fold this disk's observed MB/s into the per-pool-pair EWMA, so the
        ETA estimate self-corrects as the run proceeds."""
        started = item.get("move_started_at")
        size = int(item.get("size_bytes") or 0)
        if not started or size <= 0:
            return
        elapsed = max(time() - float(started), 0.001)
        mbps = size / elapsed / 1_000_000
        key = f"{self._pool_of(item['src_path']).id}:{self.dst_pool.id}"
        ewma = dict(self.migration.throughput_ewma or {})
        ewma[key] = mig.ewma_update(ewma.get(key), mbps)
        self.migration.throughput_ewma = ewma

    def _publish_progress(self):
        """Best-effort XADD of a migration progress event so the change-handler
        emits the aggregate ``storage:migration`` SocketIO event. Never fails
        the tick — the ledger (not the socket) is the source of truth."""
        try:
            conn = redis.from_url(rq_url())
            conn.xadd(
                TASK_RESULTS_STREAM,
                {"kind": "migration", "migration_id": self.migration_id},
                maxlen=TASK_RESULTS_STREAM_MAXLEN,
                approximate=True,
            )
        except Exception:
            log.exception(
                "migration: could not publish progress event for %s",
                self.migration_id,
            )

    def _skip_tree(self, tree_items, state, reason):
        for it in tree_items:
            self._set(it, state=state, error=reason)

    def _gate_tree(self, tree_items):
        """Tree-level quiesce gate, evaluated BEFORE the tree starts moving.

        A running disk pins its whole tree: moving an ancestor would orphan the
        running disk's backing chain, and the running disk itself cannot rebase.
        So if ANY disk in the tree is not quiescable we must decide for the
        WHOLE tree up front (never partially migrate). Returns True when the
        tree is fully stopped and phase A may proceed.
        """
        # Only gate before the tree has started; once moving, never re-gate.
        if any(
            str(it["state"]) != MigrationItemState.PENDING.value for it in tree_items
        ):
            return True
        force = bool(self.config.get("force_stop_desktops"))
        running = []
        for it in tree_items:
            for d in self._domains(it["storage_id"]):
                if mig.quiesce_decision(d.status, force) != "ok":
                    running.append(d)
        if not running:
            return True
        if not force:
            self._skip_tree(
                tree_items,
                MigrationItemState.SKIPPED.value,
                "tree has a running desktop and force-stop was not requested",
            )
            return False
        # force-stop: request a stop on every still-running domain, bounded so a
        # desktop that never stops fails the tree instead of looping forever.
        for d in running:
            if d.status == "Started":
                try:
                    d.status = "Stopping"
                except Exception:
                    log.exception("migration: force-stop failed on domain %s", d.id)
        attempts = max(int(it.get("attempts") or 0) for it in tree_items) + 1
        if attempts > QUIESCE_MAX_ATTEMPTS:
            self._skip_tree(
                tree_items,
                MigrationItemState.FAILED.value,
                "force-stop did not stop the tree's desktops in time",
            )
            return False
        for it in tree_items:
            self._set(it, attempts=attempts)
        return False

    # -- per-disk actions -------------------------------------------------- #
    def _restore_storage_status(self, item):
        """Restore a disk's storage to the status it held BEFORE we set it to
        maintenance (recorded at move start). Only disks we actually put into
        maintenance carry a recorded original, so an untouched disk (a
        never-started pending one) is left alone — never blindly forced to
        ``ready``, which would un-bin a ``recycled`` disk (saga-5)."""
        orig = item.get("storage_orig_status")
        if orig is None:
            return
        try:
            Storage.update_document(
                item["storage_id"], {"status": orig}, validate=False
            )
        except Exception:
            log.exception(
                "migration: could not restore status on %s", item["storage_id"]
            )

    def _start_move(self, item):
        # Record the storage's pre-migration status ONCE (before maintenance) so
        # release/failure restore the ORIGINAL status rather than a hardcoded
        # "ready" that would un-bin a recycled disk (saga-5).
        if item.get("storage_orig_status") is None:
            try:
                cur = Storage(item["storage_id"]).status
            except Exception:
                cur = None
            if cur and cur != "maintenance":
                self._set(item, storage_orig_status=cur)
        # Per-disk maintenance marker (durable storage-layer start-block).
        # NOT set_maintenance("move") — that refuses a parent-with-children;
        # migration legitimately moves parents (children rebase afterwards).
        try:
            Storage.update_document(
                item["storage_id"], {"status": "maintenance"}, validate=False
            )
        except Exception:
            log.exception(
                "migration: could not set maintenance on %s", item["storage_id"]
            )
        bwlimit = int(self.config.get("bwlimit_kbs") or 0)
        task_id = self._enqueue(
            "move",
            self._move_queue(item["src_path"]),
            {
                "origin_path": item["src_path"],
                "destination_path": item["dst_path"],
                "method": "rsync",
                "bwlimit": bwlimit,
                "remove_source_file": False,  # keep source until release
            },
            timeout=RSYNC_TIMEOUT,
        )
        self._set(
            item,
            state=MigrationItemState.MOVING.value,
            move_task_id=task_id,
            move_started_at=time(),
        )

    def _mark_moved(self, item):
        self._record_throughput(item)
        self._set(item, state=MigrationItemState.MOVED.value)

    def _skip_move(self, item):
        # dst == src (same-pool, or already in the destination pool): the file is
        # already at its destination. Skip the rsync entirely — and the
        # maintenance marker, since nothing physically moves (the job-wide
        # autostart guard and the quiesce gate already protect the disk). Advance
        # straight to moved so any rebase/db_update still runs.
        self._set(item, state=MigrationItemState.MOVED.value)

    def _start_rebase(self, item):
        task_id = self._enqueue(
            "rebase",
            self._pool_queue(item["dst_path"]),
            {
                "child_path": item["dst_path"],
                "new_backing_path": item["parent_dst_path"],
                # qemu_img_check the rebased chain before advancing (the disks
                # live on the storage worker, so the verify runs there).
                "verify": bool(self.config.get("verify", True)),
            },
        )
        self._set(item, rebase_task_id=task_id)

    def _mark_rebased(self, item):
        self._set(item, state=MigrationItemState.REBASED.value)

    def _skip_rebase(self, item):
        self._set(item, state=MigrationItemState.REBASED.value)

    def _db_update(self, item):
        # Re-point the storage row at the disk's new location. RethinkDB
        # deep-merges, so the qemu-img-info.filename update preserves
        # actual-size / virtual-size.
        Storage.update_document(
            item["storage_id"],
            {
                "directory_path": item["dst_dir"],
                "qemu-img-info": {"filename": item["dst_path"]},
            },
            validate=False,
        )
        self._set(item, state=MigrationItemState.DB_UPDATED.value)

    def _release(self, item):
        # Whole tree is committed by now (tree_next only reaches release once
        # every disk is db_updated), so deleting the source cannot orphan a
        # not-yet-rebased child. Restore the storage to its ORIGINAL status
        # (saga-5: not hardcoded "ready"), then delete the source LAST.
        self._restore_storage_status(item)
        del_task_id = self._enqueue(
            "move_delete",
            self._pool_queue(item["src_path"]),
            {"path": item["src_path"]},
        )
        self._set(
            item,
            state=MigrationItemState.RELEASED.value,
            move_delete_task_id=del_task_id,
        )

    def _skip_release(self, item):
        # dst == src: there is no separate source to delete — move_delete would
        # destroy the live disk in place. The disk was never moved (so never set
        # to maintenance); just mark it released.
        self._set(item, state=MigrationItemState.RELEASED.value)

    def _terminalize_tree_failure(self, item):
        """A disk's move/rebase failed (action ``fail``) or it is already failed
        and blocks its tree (action ``blocked``). Terminalize the WHOLE tree so
        the job can finish and ``reactivate()`` runs (autostart restored),
        instead of wedging: the failed disk -> failed, its descendants and the
        rest of the tree -> skipped (abandoned, sources retained). Each affected
        disk's storage is taken out of maintenance back to its original status
        (qcow-1 / scheduler-1 / qcow-3 / saga-5)."""
        tree_items = [it for it in self._items() if it["tree_id"] == item["tree_id"]]
        # The triggering disk may already be `failed` (set by the generic
        # exception handler), which plan_tree_failure leaves untouched — reset
        # its storage explicitly so it never stays stuck in maintenance.
        self._restore_storage_status(item)
        for it, new_state, reason in mig.plan_tree_failure(
            tree_items, item["storage_id"]
        ):
            self._restore_storage_status(it)
            self._set(it, state=new_state, error=reason)

    def _fail(self, item):
        self._terminalize_tree_failure(item)

    def _blocked(self, item):
        self._terminalize_tree_failure(item)

    _ACTIONS = {
        "start_move": _start_move,
        "skip_move": _skip_move,
        "mark_moved": _mark_moved,
        "start_rebase": _start_rebase,
        "mark_rebased": _mark_rebased,
        "skip_rebase": _skip_rebase,
        "db_update": _db_update,
        "release": _release,
        "skip_release": _skip_release,
        "fail": _fail,
        "blocked": _blocked,
    }

    # -- tick -------------------------------------------------------------- #
    def tick(self):
        """Advance every tree by at most one step. Returns a list of
        ``(tree_id, item_id|None, action)`` describing what happened."""
        # Cancel = finish-current-tree (P2.4): once an admin cancels, the job is
        # in finishing_tree — stop starting new trees (skip the not-started
        # ones), let in-flight trees finish, then flip to canceled.
        finishing = str(self.migration.status) == MigrationStatus.FINISHING_TREE.value

        # Mandatory autostart guard: deactivate autostart for the whole job
        # before any disk is touched (idempotent — only un-prepared items). When
        # finishing we never start new trees, so don't suppress autostart for the
        # not-started trees we are about to skip.
        if not finishing:
            self.prepare()
        items = self._items()
        trees = {}
        for it in items:
            trees.setdefault(it["tree_id"], []).append(it)

        # Window + ETA admission gate (P2.2): a not-yet-started tree only begins
        # inside the window and only if its ETA fits; in-flight trees always run
        # to completion (respecting the 12h move-task timeout), never abandoned
        # mid-chain when the window closes.
        has_window, win_open, remaining_s = self._window_state()

        # Parallelism gate (P2.3): bound concurrent trees to config.parallelism
        # so the storage worker is not oversubscribed. In-flight trees keep
        # advancing; only STARTING a new tree consumes a slot.
        phases = {
            tid: mig.tree_phase([it["state"] for it in tis])
            for tid, tis in trees.items()
        }
        slots = mig.admission_slots(
            list(phases.values()), self.config.get("parallelism")
        )

        results = []
        for tree_id, tree_items in trees.items():
            if phases[tree_id] == "not_started":
                if finishing:
                    # Canceling: a tree that has not moved any disk is skipped
                    # cleanly rather than started.
                    self._skip_tree(
                        tree_items,
                        MigrationItemState.SKIPPED.value,
                        "canceled before tree started",
                    )
                    results.append((tree_id, None, "canceled"))
                    continue
                if slots <= 0 or not self._admit_tree(
                    tree_items, win_open, remaining_s
                ):
                    results.append((tree_id, None, "deferred"))
                    continue
                slots -= 1  # this tree starts now, consuming a slot
            if not self._gate_tree(tree_items):
                results.append((tree_id, None, "gated"))
                continue
            item, action = mig.tree_next(tree_items, self.job_status_fn)
            results.append((tree_id, item["id"] if item else None, action))
            handler = self._ACTIONS.get(action)
            if handler is not None:
                try:
                    handler(self, item)
                except Exception:
                    log.exception(
                        "migration: action %s failed on item %s",
                        action,
                        item.get("id") if item else None,
                    )
                    if item:
                        self._set(
                            item,
                            state=MigrationItemState.FAILED.value,
                            error=f"action {action} raised",
                        )
        self.migration.recompute_totals()
        if self.is_complete():
            # Crash-safe re-activation from the ledger, then mark the job done.
            # A finishing (canceled) job becomes canceled, not completed, even
            # though its in-flight trees finished cleanly.
            self.reactivate()
            failed = any(
                str(it["state"]) == MigrationItemState.FAILED.value
                for it in self._items()
            )
            if finishing:
                self.migration.status = MigrationStatus.CANCELED.value
            else:
                self.migration.status = (
                    MigrationStatus.FAILED.value
                    if failed
                    else MigrationStatus.COMPLETED.value
                )
        else:
            # Flip running<->window_closed by the window; never clobber a paused
            # /finishing/terminal status (the driver only ticks running + the
            # window_closed it set here).
            cur = str(self.migration.status)
            if cur in (
                MigrationStatus.RUNNING.value,
                MigrationStatus.WINDOW_CLOSED.value,
            ):
                target = (
                    MigrationStatus.WINDOW_CLOSED.value
                    if (has_window and not win_open)
                    else MigrationStatus.RUNNING.value
                )
                if cur != target:
                    self.migration.status = target
        # Surface the live window for the admin UI.
        self.migration.current_window = {
            "has_window": has_window,
            "open": win_open,
            "remaining_seconds": (
                None if remaining_s == float("inf") else int(remaining_s)
            ),
        }
        # Signal the change-handler to broadcast the aggregate to admins.
        self._publish_progress()
        return results

    def is_complete(self):
        """True when every item is terminal (released/skipped/failed)."""
        items = self._items()
        return all(
            str(it["state"])
            in (
                MigrationItemState.RELEASED.value,
                MigrationItemState.SKIPPED.value,
                MigrationItemState.FAILED.value,
            )
            for it in items
        )
