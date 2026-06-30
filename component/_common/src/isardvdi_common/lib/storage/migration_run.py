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

from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.models.storage import Storage, get_queue_from_storage_pools
from isardvdi_common.models.storage_migration import (
    MigrationItemState,
    StorageMigration,
    StorageMigrationItem,
)
from isardvdi_common.models.storage_pool import StoragePool
from isardvdi_common.models.task import Task

log = logging.getLogger(__name__)

DEFAULT_PRIORITY = "default"
RSYNC_TIMEOUT = 43200  # 12h, matching Storage.rsync


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
        items = self._items()
        trees = {}
        for it in items:
            trees.setdefault(it["tree_id"], []).append(it)

        results = []
        for tree_id, tree_items in trees.items():
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
