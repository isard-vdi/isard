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

"""Aggregate ``storage:migration`` SocketIO emit for the admin migration view.

Modeled on :func:`task_results.storage.send_status_socket` (write-only admin
fan-out via the shared :class:`AsyncRedisManager`), NOT on
``emit_task_feedback`` (which is per-user task-progress). The reconciler signals
progress by XADD-ing a ``{kind: "migration", migration_id}`` entry to
``stream:task-results``; the stream consumer dispatches it here, and this builds
the aggregate (one row per ROOT tree + job totals, COUNT(items WHERE state)) and
broadcasts it to ``/administrators`` so the storage-pools admin view live-updates.
"""

import asyncio
import json
import logging as log

from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.models.storage_migration import (
    StorageMigration,
    StorageMigrationItem,
)


def _build_payload(migration_id):
    """Aggregate the migration ledger into the admin-view shape via the shared
    :func:`isardvdi_common.lib.storage.migration.aggregate_status`, so the socket
    event and the apiv4 status endpoint render identically. Everything is derived
    (COUNT(items WHERE state=X)) — never an incremental counter. Returns ``None``
    when the migration no longer exists (nothing to emit)."""
    if not StorageMigration.exists(migration_id):
        return None
    m = StorageMigration(migration_id)
    items = StorageMigrationItem.dicts_by_migration(migration_id)
    return mig.aggregate_status(m, items)


async def send_migration_socket(redis_manager, migration_id):
    """Broadcast the migration aggregate as the ``storage:migration`` event to
    the ``/administrators`` admins room (admin-only feature). Best-effort: a
    failed emit is logged, never propagated."""
    payload = await asyncio.to_thread(_build_payload, migration_id)
    if payload is None:
        return
    body = json.dumps(payload)
    try:
        await redis_manager.emit(
            "storage:migration",
            body,
            namespace="/administrators",
            room="admins",
        )
    except Exception:
        log.exception(
            "task_results.migration: emit storage:migration for %s failed",
            migration_id,
        )
