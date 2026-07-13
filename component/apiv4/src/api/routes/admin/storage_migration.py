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

"""Admin storage-disk migration endpoints (I+D #1924).

Plan / create / list / status / control (start, pause, cancel) / config for the
path->path migration, plus the pool-scoped aggregation overview. All admin-only
(``admin_router`` ⇒ ``is_admin``). Business logic lives in the service +
``isardvdi_common.lib.storage.migration``; these handlers only validate, run the
sync service off the event loop, and shape the response.
"""

import asyncio
import json
import traceback
from typing import Literal, Optional

from api import admin_router
from api.schemas.admin.storage_migration import (
    MigrationConfigData,
    MigrationCreateData,
    MigrationListResponse,
    MigrationPathPrefixesResponse,
    MigrationPlanData,
    MigrationPlanResponse,
    MigrationResponse,
    MigrationStatusResponse,
    PoolPlanResponse,
)
from api.schemas.common import ErrorResponse
from api.services.admin.storage_migration import AdminStorageMigrationService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import Response

_TAGS = ["admin-storage-migration"]
_ERRS = {400: {"model": ErrorResponse}, 500: {"model": ErrorResponse}}


@admin_router.post(
    "/admin/storage/migrations/plan",
    tags=_TAGS,
    response_model=MigrationPlanResponse,
    summary="Preview a storage-disk migration plan (dry run)",
    description="Resolve the selection and return what would move, grouped by "
    "root tree. Nothing is persisted.",
    responses=_ERRS,
)
async def admin_storage_migration_plan(request: Request, data: MigrationPlanData):
    try:
        return await asyncio.to_thread(
            AdminStorageMigrationService.plan, data.selection.model_dump()
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to build migration plan",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/storage/migrations",
    tags=_TAGS,
    response_model=MigrationResponse,
    summary="Create a storage-disk migration job",
    description="Resolve + persist a migration (status planned) and its per-disk "
    "ledger rows.",
    responses=_ERRS,
)
async def admin_storage_migration_create(request: Request, data: MigrationCreateData):
    try:
        return await asyncio.to_thread(
            AdminStorageMigrationService.create,
            request.token_payload,
            data.selection.model_dump(),
            data.config.model_dump(),
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create migration",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/storage/migrations",
    tags=_TAGS,
    response_model=MigrationListResponse,
    summary="List storage-disk migration jobs",
    responses=_ERRS,
)
async def admin_storage_migration_list(request: Request):
    try:
        migrations = await asyncio.to_thread(AdminStorageMigrationService.list)
        return {"migrations": migrations}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list migrations",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/storage/migrations/path-prefixes",
    tags=_TAGS,
    response_model=MigrationPathPrefixesResponse,
    summary="List real source path-prefixes for the path selection kind",
    description="Distinct storage.directory_path values (optionally scoped to a "
    "source pool) that populate the path-migration dropdown. Read-only.",
    responses=_ERRS,
)
async def admin_storage_migration_path_prefixes(
    request: Request, src_pool_id: Optional[str] = None
):
    # Registered BEFORE the /{migration_id} route so "path-prefixes" is not
    # captured as a migration id.
    try:
        return await asyncio.to_thread(
            AdminStorageMigrationService.path_prefixes, src_pool_id
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list path prefixes",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/storage/migrations/{migration_id}/log",
    tags=_TAGS,
    summary="Download a storage-disk migration report (CSV or JSON)",
    description="A downloadable per-disk audit of what was moved / failed / "
    "skipped / quarantined / in-place, annotated by occurrence for recurring "
    "jobs, with a summary header. format=csv (default) | json.",
    responses=_ERRS,
    response_class=Response,
)
async def admin_storage_migration_log(
    request: Request,
    migration_id: str,
    format: Literal["csv", "json"] = "csv",
):
    # Registered before the /{migration_id} status route is irrelevant here (this
    # is a distinct two-segment path), but a download returns a raw Response with
    # Content-Disposition rather than a response_model.
    try:
        if format == "json":
            payload = await asyncio.to_thread(
                AdminStorageMigrationService.log, migration_id
            )
            return Response(
                content=json.dumps(payload, indent=2),
                media_type="application/json",
                headers={
                    "Content-Disposition": (
                        f'attachment; filename="migration-{migration_id}.json"'
                    )
                },
            )
        body = await asyncio.to_thread(
            AdminStorageMigrationService.log_csv, migration_id
        )
        return Response(
            content=body,
            media_type="text/csv",
            headers={
                "Content-Disposition": (
                    f'attachment; filename="migration-{migration_id}.csv"'
                )
            },
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to build migration log",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/storage/migrations/{migration_id}",
    tags=_TAGS,
    response_model=MigrationStatusResponse,
    summary="Storage-disk migration status (live ledger aggregate)",
    responses=_ERRS,
)
async def admin_storage_migration_status(request: Request, migration_id: str):
    try:
        return await asyncio.to_thread(
            AdminStorageMigrationService.status, migration_id
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to read migration status",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/storage/migrations/{migration_id}/{action}",
    tags=_TAGS,
    response_model=MigrationResponse,
    summary="Control a storage-disk migration (start, pause, cancel)",
    responses=_ERRS,
)
async def admin_storage_migration_action(
    request: Request,
    migration_id: str,
    action: Literal["start", "pause", "cancel"],
):
    try:
        return await asyncio.to_thread(
            AdminStorageMigrationService.set_action, migration_id, action
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to {action} migration",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/storage/migrations/{migration_id}/config",
    tags=_TAGS,
    response_model=MigrationResponse,
    summary="Update a storage-disk migration's config",
    responses=_ERRS,
)
async def admin_storage_migration_config(
    request: Request, migration_id: str, data: MigrationConfigData
):
    try:
        return await asyncio.to_thread(
            AdminStorageMigrationService.update_config,
            migration_id,
            data.model_dump(),
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update migration config",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/storage-pool/{pool_id}/migration/plan",
    tags=_TAGS,
    response_model=PoolPlanResponse,
    summary="Pool-scoped migration aggregation (root-tree overview)",
    description="Enumerate the pool's root trees with per-tree derivative / "
    "desktop / byte counts for the admin overview.",
    responses=_ERRS,
)
async def admin_storage_pool_migration_plan(request: Request, pool_id: str):
    try:
        return await asyncio.to_thread(AdminStorageMigrationService.pool_plan, pool_id)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to build pool migration plan",
            traceback.format_exc(),
        )
