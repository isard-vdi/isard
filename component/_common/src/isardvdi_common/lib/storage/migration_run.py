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
from os.path import dirname

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
        ledger on resume). Idempotent: only items not yet recorded are touched.
        """
        to_deactivate = []
        for item in self._items():
            if item.get("autostart_domains") is not None:
                continue  # already prepared
            records = []
            for dom in self._domains(item["storage_id"]):
                was_on = bool(getattr(dom, "server_autostart", False))
                records.append({"id": dom.id, "was_on": was_on})
                if was_on:
                    to_deactivate.append(dom.id)
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
    def _start_move(self, item):
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
        self._set(item, state=MigrationItemState.MOVING.value, move_task_id=task_id)

    def _mark_moved(self, item):
        self._set(item, state=MigrationItemState.MOVED.value)

    def _start_rebase(self, item):
        task_id = self._enqueue(
            "rebase",
            self._pool_queue(item["dst_path"]),
            {
                "child_path": item["dst_path"],
                "new_backing_path": item["parent_dst_path"],
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
        # not-yet-rebased child. Restore the storage to ready, then delete the
        # source LAST.
        try:
            Storage.update_document(
                item["storage_id"], {"status": "ready"}, validate=False
            )
        except Exception:
            log.exception("migration: could not set ready on %s", item["storage_id"])
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

    _ACTIONS = {
        "start_move": _start_move,
        "mark_moved": _mark_moved,
        "start_rebase": _start_rebase,
        "mark_rebased": _mark_rebased,
        "skip_rebase": _skip_rebase,
        "db_update": _db_update,
        "release": _release,
    }

    # -- tick -------------------------------------------------------------- #
    def tick(self):
        """Advance every tree by at most one step. Returns a list of
        ``(tree_id, item_id|None, action)`` describing what happened."""
        # Mandatory autostart guard: deactivate autostart for the whole job
        # before any disk is touched (idempotent — only un-prepared items).
        self.prepare()
        items = self._items()
        trees = {}
        for it in items:
            trees.setdefault(it["tree_id"], []).append(it)

        results = []
        for tree_id, tree_items in trees.items():
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
            self.reactivate()
            failed = any(
                str(it["state"]) == MigrationItemState.FAILED.value
                for it in self._items()
            )
            self.migration.status = (
                MigrationStatus.FAILED.value
                if failed
                else MigrationStatus.COMPLETED.value
            )
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
