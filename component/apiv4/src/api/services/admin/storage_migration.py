#
#   Copyright © 2026 IsardVDI
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Admin storage-disk migration service.

Thin orchestration over ``isardvdi_common.lib.storage.migration`` (the plan /
selection / aggregation logic) and the ``StorageMigration`` /
``StorageMigrationItem`` ledger models. No DB driver calls live here.
"""

from time import time

from api.services.error import Error
from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.models.storage_migration import (
    MigrationStatus,
    StorageMigration,
    StorageMigrationItem,
)
from isardvdi_common.models.storage_pool import StoragePool

#: admin-driven status transitions exposed through the `{action}` route
_ACTION_TARGET = {
    "start": MigrationStatus.RUNNING.value,
    "pause": MigrationStatus.PAUSED.value,
    "cancel": MigrationStatus.CANCELED.value,
}
#: a job in one of these terminal states can no longer be controlled
_TERMINAL = {
    MigrationStatus.COMPLETED.value,
    MigrationStatus.FAILED.value,
    MigrationStatus.CANCELED.value,
}


def _tree_summaries(items):
    by_tree = {}
    for it in items:
        by_tree.setdefault(it["tree_id"], []).append(it)
    out = []
    for tree_id, tit in by_tree.items():
        s = mig.summarize_plan(tit)
        out.append(
            {
                "tree_id": tree_id,
                "root_storage_id": tree_id,
                "derivative_templates": s["derivative_templates"],
                "desktops": s["desktops"],
                "media": s["media"],
                "items_total": s["items_total"],
                "bytes_total": s["bytes_total"],
            }
        )
    return out


def _serialize(m: StorageMigration) -> dict:
    """Shape a ``StorageMigration`` object as an API dict (attrs are cached on
    construction, so this is cheap)."""
    return {
        "id": m.id,
        "status": m.status,
        "selection": m.selection or {},
        "config": m.config or {},
        "totals": m.totals or {},
        "created_by": m.created_by,
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }


class AdminStorageMigrationService:
    """Admin storage-disk migration orchestration."""

    @staticmethod
    def _dst_pool(selection: dict) -> StoragePool:
        dst_id = selection.get("dst_pool_id")
        if not dst_id:
            raise Error("bad_request", "A destination storage pool is required")
        if not StoragePool.exists(dst_id):
            raise Error("not_found", f"Destination storage pool {dst_id} not found")
        return StoragePool(dst_id)

    @classmethod
    def plan(cls, selection: dict) -> dict:
        """Dry-run preview — resolve the selection, build the plan, summarise
        per tree. Nothing is persisted."""
        dst_pool = cls._dst_pool(selection)
        roots = mig.roots_for_selection(selection)
        items, totals = mig.build_plan_for_roots("__preview__", roots, dst_pool)
        return {"trees": _tree_summaries(items), "totals": totals}

    @classmethod
    def create(cls, payload: dict, selection: dict, config: dict) -> dict:
        """Resolve + build + persist a migration job (status ``planned``) and
        its per-disk ledger rows. Idempotent on re-plan (deterministic ids)."""
        dst_pool = cls._dst_pool(selection)
        roots = mig.roots_for_selection(selection)
        if not roots:
            raise Error("bad_request", "Selection matched no migratable disks")
        now = time()
        migration = StorageMigration.init_document(
            status=MigrationStatus.PLANNED.value,
            selection=selection,
            config=config,
            totals={},
            created_by=payload.get("user_id"),
            created_at=now,
            updated_at=now,
        )
        items, totals = mig.build_plan_for_roots(migration.id, roots, dst_pool)
        for item in items:
            StorageMigrationItem.upsert(item)
        migration.totals = totals
        return cls.get(migration.id)

    @staticmethod
    def list() -> list:
        return [_serialize(m) for m in StorageMigration.get_all()]

    @staticmethod
    def get(migration_id: str) -> dict:
        if not StorageMigration.exists(migration_id):
            raise Error("not_found", f"Migration {migration_id} not found")
        return _serialize(StorageMigration(migration_id))

    @staticmethod
    def status(migration_id: str) -> dict:
        if not StorageMigration.exists(migration_id):
            raise Error("not_found", f"Migration {migration_id} not found")
        m = StorageMigration(migration_id)
        items = StorageMigrationItem.dicts_by_migration(migration_id)
        totals = m.recompute_totals()  # live COUNT(items WHERE state=X)
        return {
            "id": m.id,
            "status": m.status,
            "totals": totals,
            "state_counts": StorageMigrationItem.state_counts(migration_id),
            "trees": _tree_summaries(items),
        }

    @classmethod
    def set_action(cls, migration_id: str, action: str) -> dict:
        if not StorageMigration.exists(migration_id):
            raise Error("not_found", f"Migration {migration_id} not found")
        m = StorageMigration(migration_id)
        if m.status in _TERMINAL:
            raise Error(
                "precondition_required",
                f"Migration {migration_id} is {m.status} and can no longer be {action}ed",
            )
        m.status = _ACTION_TARGET[action]
        m.updated_at = time()
        return cls.get(migration_id)

    @classmethod
    def update_config(cls, migration_id: str, config: dict) -> dict:
        if not StorageMigration.exists(migration_id):
            raise Error("not_found", f"Migration {migration_id} not found")
        m = StorageMigration(migration_id)
        if m.status in _TERMINAL:
            raise Error(
                "precondition_required",
                f"Migration {migration_id} is {m.status}; config is immutable",
            )
        m.config = config
        m.updated_at = time()
        return cls.get(migration_id)

    @staticmethod
    def pool_plan(pool_id: str) -> dict:
        if not StoragePool.exists(pool_id):
            raise Error("not_found", f"Storage pool {pool_id} not found")
        return mig.pool_plan_summary(pool_id)
