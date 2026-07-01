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
from rq.registry import StartedJobRegistry

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
#: A STARTED storage job whose worker DIED keeps its rq status STARTED until the
#: 12h task timeout — rq never flips it, because the only thing that changes is
#: that its StartedJobRegistry heartbeat score stops being refreshed. Treat such
#: a job as ABANDONED only once that score expired at least ABANDON_GRACE_S ago,
#: so a momentarily-stalled LIVE worker (a GC/IO pause) is never misjudged (no
#: false positive). rq refreshes the score ~every job_monitoring_interval to
#: now+~90s, so a live worker's score is always well in the future.
ABANDON_GRACE_S = 30
#: Bound the orphan-RESUME: after this many abandonment-driven re-enqueues of a
#: single disk's task, terminalize instead of resuming forever (a task whose
#: worker keeps dying — e.g. a poisoned host — must not loop). Mirrors the
#: QUIESCE_MAX_ATTEMPTS retry-bound pattern; resume is the default, this is the
#: safety net, so the first abandonment always RESUMES.
MAX_ABANDON_RESTARTS = 10


def job_status(task_id):
    """Failure-aware RQ status of a migration task id, or ``None`` if absent.

    A storage task can fail in TWO ways that rq's ``Job.get_status()`` does not
    report as ``failed`` — both caused silent data loss until handled here:

    1. **Raised.** The worker preserves the traceback in ``job.exc_info`` and
       publishes the failure on ``stream:task-results``, but ``get_status()``
       still returns ``finished`` (verified live: a raising ``task.move`` ends
       ``status=finished, exc_info set``). So any job carrying ``exc_info`` is a
       failure.

    2. **Non-zero return without raising.** ``move`` runs rsync via
       ``run_with_progress``, which RETURNS the process exit code on a non-cancel
       non-zero exit (e.g. the destination pool fills mid-copy -> rc 11/23)
       instead of raising. The job is then ``finished``/``exc_info=None`` with a
       non-zero int return value — a failed move that would otherwise be marked
       ``moved`` and (for a ROOT disk, which skips the rebase check) reach release
       and ``move_delete`` the live source against an absent/partial destination.
       So a finished task whose return value is a non-zero int is a failure too.
       ``rebase``/``migration_verify_destination`` only ever return 0 or raise,
       so this never false-positives on them; and ``job_status`` is migration-
       only, so shared ``move`` behaviour for other callers is untouched.

    Classifying both as ``"failed"`` makes ``_job_failed`` fire so the tree
    terminalizes (sources retained). The unconditional pre-release destination
    gate (``migration_verify_destination``) is the backstop for any move that
    still reports success against a bad destination.

    A THIRD case needs ``None`` (not ``failed``): a STARTED job whose WORKER
    DIED. rq keeps it STARTED until the 12h task timeout (only its heartbeat
    score stops refreshing), so the saga would wedge. Reporting it GONE
    (``None``) makes ``decide_item_action`` / ``verify_gate_state`` re-enqueue
    the idempotent task — orphan RESUME — exactly as for a redis-expired job.
    Resume is migration-scoped (the move/rebase/verify tasks are idempotent);
    a general resume reaper would be unsafe for relative-resize / in-place
    convert/sparsify tasks, so this lives only here.

    BEST-EFFORT: this detection races rq's own ``StartedJobRegistry.cleanup``,
    which a LIVE worker runs during periodic maintenance (<= ~600s) and which
    flips an abandoned STARTED job to ``failed`` (moving it to the
    FailedJobRegistry). Whichever fires first wins: if we observe ``None`` first
    the disk RESUMES; if rq's cleanup wins, the job reads ``failed`` here and the
    tree terminalizes (sources retained) — the bounded-resume terminalize branch
    is the deliberate SAFE FALLBACK, not a bug. Either outcome is data-loss-safe.
    """
    if not task_id:
        return None
    try:
        if not Task.exists(task_id):
            return None
        task = Task(task_id)
        # exc_info is populated only when the task function raised; that is the
        # reliable failure signal regardless of the (misleading) rq status.
        if task.exc_info:
            return "failed"
        status = task.job_status
        # A move that rsync-failed returned a non-zero rc WITHOUT raising.
        if mig._job_finished(status):
            result = task.result
            if isinstance(result, int) and not isinstance(result, bool) and result != 0:
                return "failed"
            return status
        # A STARTED job whose worker died is abandoned -> report it GONE so the
        # reconciler RESUMES (re-enqueues) it rather than waiting out the 12h
        # timeout. Only STARTED can be orphaned; queued/deferred just wait.
        if status == "started" and _job_abandoned(task):
            return None
        return status
    except Exception:
        return None


def _job_abandoned(task):
    """True when a STARTED job's worker has DIED.

    rq's worker refreshes each running job's score in the per-queue
    ``StartedJobRegistry`` every monitoring interval; when the worker dies the
    score stops moving and slips into the past. ``get_expired_job_ids(cutoff)``
    returns jobs whose score is below ``cutoff``; using ``now - ABANDON_GRACE_S``
    means the job must have been expired for at least the grace margin, so a
    briefly-stalled LIVE worker is never flagged. Uses the same redis-from-url
    pattern as the change-handler reconciler.

    BEST-EFFORT and racy by design: rq's own ``StartedJobRegistry.cleanup`` (run
    by a live worker's periodic maintenance, <= ~600s) reaps the same expired
    score into the FailedJobRegistry. If it wins, ``job_status`` reads the job as
    ``failed`` and the tree terminalizes via the bounded-resume fallback instead
    of resuming — still data-loss-safe (sources retained), so the race is benign.
    """
    try:
        conn = redis.from_url(rq_url())
        registry = StartedJobRegistry(task.job.origin, connection=conn)
        cutoff = time() - ABANDON_GRACE_S
        return task.id in registry.get_expired_job_ids(cutoff)
    except Exception:
        # Never let a redis/registry hiccup flip a live job to GONE.
        return False


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

        Crash-safe ordering (qcow-2): persist the ledger records FIRST (was_on =
        the current live value), and only THEN deactivate. Deactivating before
        persisting would let a crash in between re-read the now-False field and
        record was_on=False -> permanent autostart loss; persisting first keeps
        the pre-suppression value durable for reactivate. The deactivation set is
        re-derived from the full ledger every prepare (so a crash between persist
        and deactivate re-suppresses on resume) but filtered to the still-live
        domains, so deactivate_autostart neither re-fires/re-notifies every tick
        nor misses a crash-interrupted suppression.
        """
        writes, to_deactivate = mig.plan_autostart_deactivation(
            self._items(), self._domains
        )
        for item, records in writes:
            self._set(item, autostart_domains=records)
        if to_deactivate:
            DesktopEvents.deactivate_autostart(to_deactivate)

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
        configured maintenance window, honouring selected weekdays. A window
        exists when it has a time range and/or a day filter; with neither the job
        is always open/unbounded. Empty ``days`` imposes no day restriction, so a
        pre-schedule (time-only) job behaves exactly as before."""
        window = (self.config or {}).get("window") or {}
        start = mig.parse_hhmm(window.get("start"))
        end = mig.parse_hhmm(window.get("end"))
        days = window.get("days") or []
        dset = mig.normalize_days(days)
        has_window = (start is not None and end is not None) or dset is not None
        if not has_window:
            return False, True, float("inf")
        now = self._now(window.get("tz") or "UTC")
        now_min = now.hour * 60 + now.minute
        weekday = now.weekday()
        return (
            True,
            mig.window_is_open_days(start, end, days, weekday, now_min),
            mig.window_remaining_seconds_days(start, end, days, weekday, now_min),
        )

    def _next_run_seconds(self):
        """Seconds until the window next opens on a selected weekday (admin-table
        lookahead), in the window's timezone. ``None`` when there is no
        schedule."""
        window = (self.config or {}).get("window") or {}
        if not window:
            return None
        now = self._now(window.get("tz") or "UTC")
        return mig.next_run_for_window(window, now)

    # -- recurring re-scan (cadence + failure policy are per-job config) ---- #
    def _maybe_rescan_occurrence(self):
        """RECURRING re-scan. Returns True if it re-scanned this tick.

        Fires per the job's ``rescan_cadence`` (``mig.should_rescan``): ``edge``
        only at the occurrence edge, ``edge_on_drain`` also once the batch has
        drained, ``continuous`` every tick in-window. An OCCURRENCE-EDGE re-scan
        additionally re-arms failed/skipped in-scope disks (and quarantines per
        the failure policy — see ``_rearm_for_occurrence``); a between-edges
        re-scan only inserts newly-matching disks (never disturbs in-flight)."""
        if not bool(self.config.get("recurring")):
            return False
        window = (self.config or {}).get("window") or {}
        start = mig.parse_hhmm(window.get("start"))
        end = mig.parse_hhmm(window.get("end"))
        days = window.get("days") or []
        now = self._now(window.get("tz") or "UTC")
        now_min = now.hour * 60 + now.minute
        if not mig.window_is_open_days(start, end, days, now.weekday(), now_min):
            return False
        key = mig.occurrence_key(now, start, end)
        last = self.migration.last_occurrence or None
        is_edge = key != last
        cadence = self.config.get("rescan_cadence") or "edge_on_drain"
        if not mig.should_rescan(cadence, key, last, self.is_complete(), True):
            return False
        if is_edge:
            # New occurrence: re-arm failed/skipped disks (quarantine per policy)
            # AND insert newly-matching disks, keyed by this occurrence.
            self._rearm_for_occurrence(key)
            self.migration.last_occurrence = key
        else:
            # Same occurrence (continuous / on-drain): pick up new disks only.
            self._rescan_insert_new()
        return True

    def _rescan_insert_new(self):
        """Re-resolve the selection and upsert ONLY disks not already in the
        ledger (state ``pending``). Deterministic item ids mean an
        already-migrated/terminal disk is never reset back to pending; and a
        pool/path/category source scope naturally excludes disks that already left
        it, so a re-scan only ever ADDS newly-matching disks."""
        selection = self.migration.selection or {}
        roots = mig.roots_for_selection(selection)
        items, _ = mig.build_plan_for_roots(self.migration_id, roots, self.dst_pool)
        existing = {it["storage_id"] for it in self._items()}
        for item in items:
            if item["storage_id"] not in existing:
                StorageMigrationItem.upsert(item)

    def _rearm_for_occurrence(self, occurrence_key):
        """New-occurrence re-scan: insert newly-matching disks AND re-arm the
        prior occurrence's failed/skipped in-scope disks so they retry, applying
        the failure policy per tree (``mig.plan_tree_rearm``): a disk that hits the
        ``retry_quarantine`` budget is quarantined and its tree left dead; other
        failed/skipped disks are reset to pending. Released disks left the source
        scope and never reappear; in-flight disks are left untouched."""
        selection = self.migration.selection or {}
        roots = mig.roots_for_selection(selection)
        planned, _ = mig.build_plan_for_roots(self.migration_id, roots, self.dst_pool)
        existing = {it["storage_id"]: it for it in self._items()}
        policy = self.config.get("failure_policy") or "retry_quarantine"
        qafter = int(self.config.get("quarantine_after") or 3)
        # Group the re-planned disks by tree so quarantine/re-arm is tree-aware.
        by_tree = {}
        for item in planned:
            by_tree.setdefault(item["tree_id"], []).append(item)
        for planned_items in by_tree.values():
            ledger = [
                existing[p["storage_id"]]
                for p in planned_items
                if p["storage_id"] in existing
            ]
            to_quarantine, to_rearm = mig.plan_tree_rearm(ledger, policy, qafter)
            for item, occ in to_quarantine:
                self._set(
                    item,
                    state=MigrationItemState.QUARANTINED.value,
                    occurrence_failures=occ,
                    error=f"quarantined after {occ} consecutive occurrence failures",
                )
                self._audit(item, "quarantined")
            for item, occ in to_rearm:
                self._rearm_item(item, occ)
            # Insert genuinely new disks in this tree (or a brand-new tree).
            for p in planned_items:
                if p["storage_id"] not in existing:
                    StorageMigrationItem.upsert(p)

    def _rearm_item(self, item, occurrence_failures):
        """Reset a failed/skipped disk to pending for another occurrence attempt:
        clear the per-attempt task ids / maintenance marker / autostart record so
        the next attempt starts clean, preserving the append-only ``audit`` and the
        occurrence-failure count."""
        self._set(
            item,
            state=MigrationItemState.PENDING.value,
            occurrence_failures=int(occurrence_failures),
            move_task_id=None,
            move_started_at=None,
            rebase_task_id=None,
            verify_task_id=None,
            move_delete_task_id=None,
            storage_orig_status=None,
            autostart_domains=None,
            abandon_restarts=0,
            attempts=0,
            error=None,
        )

    def _audit(self, item, result):
        """Append one AUDIT record (this occurrence's outcome for the disk) to the
        item's append-only ``audit`` list, for the downloadable log. Recurring
        history is preserved across re-arms because records are appended, never
        overwritten. ``occurrence`` is the current occurrence key (or "initial"
        for a one-shot / pre-first-occurrence run)."""
        migration = getattr(self, "migration", None)
        occurrence = getattr(migration, "last_occurrence", None) or "initial"
        record = mig.build_audit_record(item, result, occurrence, time())
        audit = list(item.get("audit") or [])
        audit.append(record)
        self._set(item, audit=audit)

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
            self._audit(
                it, "skipped" if state == MigrationItemState.SKIPPED.value else "failed"
            )

    def _cancel_skip_tree(self, tree_items, reason):
        """Skip an UNCOMMITTED in-flight tree on cancel: take every disk out of
        maintenance back to its ORIGINAL status and mark it skipped — sources
        retained byte-identical, nothing move_deleted. Unlike the never-started
        cancel, these disks may already be in maintenance (a move was enqueued),
        so the status restore is mandatory; then ``is_complete`` -> ``reactivate``
        restores autostart and the job flips to canceled."""
        for it in tree_items:
            self._restore_storage_status(it)
            self._set(it, state=MigrationItemState.SKIPPED.value, error=reason)
            self._audit(it, "skipped")

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

    def _abandon_resume_blocked(self, item):
        """Bound the orphan-RESUME: count abandonment-driven re-enqueues of a
        disk's task and, once past MAX_ABANDON_RESTARTS, terminalize the tree
        instead of resuming again (a task whose worker keeps dying must not loop
        forever). Returns True when the budget is spent (caller must NOT
        re-enqueue); the first abandonment always resumes."""
        n = int(item.get("abandon_restarts") or 0) + 1
        if n > MAX_ABANDON_RESTARTS:
            self._terminalize_tree_failure(item)
            return True
        self._set(item, abandon_restarts=n)
        return False

    def _start_move(self, item):
        # A move_task_id already set means this is a RE-ENQUEUE (the prior move
        # was lost on a restart or its worker was abandoned) -> resume, bounded.
        if item.get("move_task_id") and self._abandon_resume_blocked(item):
            return
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
        # Clean phase advance: reset the orphan-resume bound so abandon_restarts
        # counts CONSECUTIVE abandonments per phase, not cumulatively across the
        # disk's whole move->rebase->db lifetime (kinder to a flaky host).
        self._set(item, state=MigrationItemState.MOVED.value, abandon_restarts=0)

    def _skip_move(self, item):
        # dst == src (same-pool, or already in the destination pool): the file is
        # already at its destination. Skip the rsync entirely — and the
        # maintenance marker, since nothing physically moves (the job-wide
        # autostart guard and the quiesce gate already protect the disk). Advance
        # straight to moved so any rebase/db_update still runs.
        self._set(item, state=MigrationItemState.MOVED.value)

    def _start_rebase(self, item):
        # rebase_task_id already set -> RE-ENQUEUE of a lost/abandoned rebase
        # (rebase -u is idempotent) -> resume, bounded.
        if item.get("rebase_task_id") and self._abandon_resume_blocked(item):
            return
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
        # Clean phase advance -> reset the orphan-resume bound (see _mark_moved).
        self._set(item, state=MigrationItemState.REBASED.value, abandon_restarts=0)

    def _skip_rebase(self, item):
        self._set(item, state=MigrationItemState.REBASED.value, abandon_restarts=0)

    def _db_update(self, item):
        # Re-point the storage row at the disk's new location. RethinkDB
        # deep-merges, so the qemu-img-info update preserves actual-size /
        # virtual-size.
        info = {"filename": item["dst_path"]}
        # saga-3: a non-root disk was rebased onto its parent's NEW path, so the
        # DB backing fields must follow too — otherwise backing-filename /
        # full-backing-filename keep pointing at the deleted old parent and
        # DB-based chain audits flag a disk/DB mismatch. The root's backing is
        # outside the migrated tree (unchanged), so leave it alone.
        if item.get("parent_dst_path"):
            info["backing-filename"] = item["parent_dst_path"]
            info["full-backing-filename"] = item["parent_dst_path"]
        Storage.update_document(
            item["storage_id"],
            {"directory_path": item["dst_dir"], "qemu-img-info": info},
            validate=False,
        )
        # Clean phase advance -> reset the orphan-resume bound so the verify
        # phase starts the consecutive-abandonment count fresh (see _mark_moved).
        self._set(item, state=MigrationItemState.DB_UPDATED.value, abandon_restarts=0)

    def _start_verify(self, item):
        # UNCONDITIONAL pre-release destination gate: prove the destination is
        # sound (exists + qemu-img check +, for a non-root, backing repointed to
        # the parent's NEW path) BEFORE the source is ever deleted. Runs on the
        # destination pool's worker (where the file lives). Read-only, so a lost
        # job is safe to re-enqueue. A root has no in-tree parent, so no backing
        # expectation; a non-root must back onto parent_dst_path.
        # verify_task_id already set -> RE-ENQUEUE of a lost/abandoned verify
        # (read-only, idempotent) -> resume, bounded.
        if item.get("verify_task_id") and self._abandon_resume_blocked(item):
            return
        task_id = self._enqueue(
            "migration_verify_destination",
            self._pool_queue(item["dst_path"]),
            {
                "dst_path": item["dst_path"],
                "expect_backing": item.get("parent_dst_path"),
            },
        )
        self._set(item, verify_task_id=task_id)

    def _release(self, item):
        # Whole tree is committed AND every destination has passed the pre-release
        # verify gate by now (tree_next only reaches release once a disk is
        # db_updated and its verify task finished), so deleting the source cannot
        # orphan a not-yet-rebased child or strand a disk on a bad destination.
        # Restore the storage to its ORIGINAL status (saga-5: not hardcoded
        # "ready"), then delete the source LAST.
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
        self._audit(item, "moved_ok")

    def _skip_release(self, item):
        # dst == src: there is no separate source to delete — move_delete would
        # destroy the live disk in place. The disk was never moved (so never set
        # to maintenance); just mark it released.
        self._set(item, state=MigrationItemState.RELEASED.value)
        self._audit(item, "in_place")

    def _terminalize_tree_failure(self, item):
        """A disk's move/rebase failed (action ``fail``) or it is already failed
        and blocks its tree (action ``blocked``). Terminalize the WHOLE tree so
        the job can finish and ``reactivate()`` runs (autostart restored),
        instead of wedging: the failed disk -> failed, its descendants and the
        rest of the tree -> skipped (abandoned, sources retained). Each affected
        disk's storage is taken out of maintenance back to its original status
        (qcow-1 / scheduler-1 / qcow-3 / saga-5)."""
        tree_items = [it for it in self._items() if it["tree_id"] == item["tree_id"]]
        # Idempotent: a tree with a failed disk keeps yielding ``blocked`` every
        # tick until the whole JOB completes, so once the tree is fully
        # terminalized do nothing — neither re-audit nor re-restore.
        if all(str(it["state"]) in mig._TERMINAL_STATES for it in tree_items):
            return
        # The triggering disk may already be `failed` (set by the generic
        # exception handler), which plan_tree_failure leaves untouched — reset
        # its storage explicitly so it never stays stuck in maintenance.
        self._restore_storage_status(item)
        changes = mig.plan_tree_failure(tree_items, item["storage_id"])
        changed_ids = {it["id"] for it, _s, _r in changes}
        # The triggering disk may already be ``failed`` (generic exception
        # handler), so plan_tree_failure leaves it untouched and out of ``changes``
        # — audit it here so its failure is still recorded exactly once.
        if item["id"] not in changed_ids and str(item["state"]) == "failed":
            self._audit(item, "failed")
        for it, new_state, reason in changes:
            self._restore_storage_status(it)
            self._set(it, state=new_state, error=reason)
            # AUDIT: the triggering disk -> failed, the rest of the tree -> skipped.
            self._audit(it, "failed" if new_state == "failed" else "skipped")

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
        "start_verify": _start_verify,
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

        # Window + ETA admission gate (P2.2): a not-yet-started tree only begins
        # inside the window and only if its ETA fits; in-flight trees always run
        # to completion (respecting the 12h move-task timeout), never abandoned
        # mid-chain when the window closes. Computed first: it gates the re-scan
        # and the autostart suppression below.
        has_window, win_open, remaining_s = self._window_state()

        # RECURRING re-scan (per rescan_cadence): re-resolve the selection and add
        # newly-matching disks (occurrence edge also re-arms failed/skipped disks
        # + quarantines per failure_policy). Runs BEFORE reading items so fresh
        # pending rows drain this same tick. No-op for a one-shot job.
        if not finishing:
            self._maybe_rescan_occurrence()

        # Mandatory autostart guard: deactivate autostart for the whole job before
        # any disk is touched (idempotent — only un-prepared items). Only while the
        # window is open (when trees may actually start): between occurrences a
        # recurring job must NOT re-suppress autostart it already restored.
        if not finishing and win_open:
            self.prepare()
        items = self._items()
        trees = {}
        for it in items:
            trees.setdefault(it["tree_id"], []).append(it)

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
        failed_this_tick = False
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
            # R2 cancel-aware skip: under cancel (finishing_tree), never START or
            # RESUME an un-started — possibly large — move/rebase/verify on a tree
            # that has committed no disk yet. Discard the in-progress work and
            # skip the tree cleanly (sources retained byte-identical, storage
            # status restored), driving the job to canceled. A tree that already
            # committed a disk still finishes normally.
            if mig.cancel_skips_tree(tree_items, action, finishing):
                self._cancel_skip_tree(tree_items, "canceled before tree committed")
                results.append((tree_id, None, "canceled"))
                continue
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
                        failed_this_tick = True
        if any(action in ("fail", "blocked") for (_t, _i, action) in results):
            failed_this_tick = True
        self.migration.recompute_totals()

        recurring = bool(self.config.get("recurring"))
        policy = self.config.get("failure_policy") or "retry_quarantine"
        fresh = self._items()
        any_failed = any(
            str(it["state"]) == MigrationItemState.FAILED.value for it in fresh
        )
        # in-flight == a disk mid-saga (not pending, not terminal): keeps a
        # recurring job "running" even once the window closed, so it finishes
        # cleanly rather than dropping to idle mid-chain.
        _settled = {
            MigrationItemState.PENDING.value,
            MigrationItemState.RELEASED.value,
            MigrationItemState.SKIPPED.value,
            MigrationItemState.FAILED.value,
            MigrationItemState.QUARANTINED.value,
        }
        any_in_flight = any(str(it["state"]) not in _settled for it in fresh)

        cur = str(self.migration.status)
        if policy == "pause" and failed_this_tick and not finishing:
            # failure_policy=pause: on any disk failure, stop driving and wait for
            # the admin. The driver does not tick paused jobs; a resume (start)
            # continues, and a recurring job re-arms the failed disk next
            # occurrence. Autostart stays suppressed (a mid-migration disk must not
            # autostart) until the job truly completes or is canceled.
            if cur != MigrationStatus.PAUSED.value:
                self.migration.status = MigrationStatus.PAUSED.value
        elif self.is_complete():
            # Set the next status only on the TRANSITION (a recurring job stays in
            # ``scheduled`` across many ticks, so guard against re-reactivating /
            # re-writing every tick): finishing -> canceled; recurring -> scheduled
            # (idle, never self-completes); one-shot -> failed/completed.
            target = mig.recurring_status_target(
                True, any_in_flight, win_open, finishing, any_failed, recurring
            )
            if cur != target:
                self.reactivate()  # crash-safe autostart restore, once per settle
                self.migration.status = target
        else:
            target = mig.recurring_status_target(
                False, any_in_flight, win_open, finishing, any_failed, recurring
            )
            if target is None:
                # one-shot: flip running<->window_closed by the window; never
                # clobber a paused/finishing/terminal status.
                if cur in (
                    MigrationStatus.RUNNING.value,
                    MigrationStatus.WINDOW_CLOSED.value,
                ):
                    target = (
                        MigrationStatus.WINDOW_CLOSED.value
                        if (has_window and not win_open)
                        else MigrationStatus.RUNNING.value
                    )
            # recurring: running (in-window/in-flight) or scheduled (idle).
            if target is not None and cur != target:
                self.migration.status = target
        # Surface the live window for the admin UI (incl. the next-run lookahead
        # for a scheduled/recurring job).
        self.migration.current_window = {
            "has_window": has_window,
            "open": win_open,
            "remaining_seconds": (
                None if remaining_s == float("inf") else int(remaining_s)
            ),
            "next_run_seconds": self._next_run_seconds(),
        }
        # Signal the change-handler to broadcast the aggregate to admins.
        self._publish_progress()
        return results

    def is_complete(self):
        """True when every item is terminal (released/skipped/failed/quarantined)."""
        items = self._items()
        return all(
            str(it["state"])
            in (
                MigrationItemState.RELEASED.value,
                MigrationItemState.SKIPPED.value,
                MigrationItemState.FAILED.value,
                MigrationItemState.QUARANTINED.value,
            )
            for it in items
        )
