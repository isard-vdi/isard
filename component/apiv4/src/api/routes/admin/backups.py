#
#   Copyright © 2025 IsardVDI
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

import asyncio
import traceback
from typing import Union

from api import admin_router
from api.schemas.admin.backups import (
    BackupConfigResponse,
    BackupIntegrityResponse,
    BackupIntegritySetRequest,
    BackupItem,
    BackupReportInsertResponse,
    BackupReportRequest,
)
from api.schemas.common import ErrorResponse
from api.services.admin.backups import AdminBackupsService
from api.services.error import Error
from fastapi import Path, Request
from fastapi.responses import JSONResponse

tag = "admin_backups"


# =============================================================================
# BACKUP LISTING
# =============================================================================


@admin_router.get(
    "/admin/items/backups",
    tags=[tag],
    response_model=Union[BackupItem, list[BackupItem]],
    summary="List backups",
    description=(
        "Get a list of backups. Optionally get a specific backup by ID via "
        "query parameter, or limit the result via the limit query parameter."
    ),
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_backups_list(request: Request):
    try:
        options = dict(request.query_params)
        if options.get("id"):
            result = await asyncio.to_thread(
                AdminBackupsService.get_backup,
                options["id"],
                pluck=options.get("pluck"),
            )
            return JSONResponse(
                content=BackupItem(**(result or {})).model_dump(mode="json"),
                status_code=200,
            )
        else:
            limit = options.get("limit")
            try:
                limit = int(limit) if limit else None
            except (TypeError, ValueError):
                raise Error("bad_request", "limit must be an integer")
            result = await asyncio.to_thread(
                AdminBackupsService.list_backups, limit=limit
            )
            return JSONResponse(
                content=[
                    BackupItem(**row).model_dump(mode="json") for row in (result or [])
                ],
                status_code=200,
            )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list backups",
            traceback.format_exc(),
        )


# =============================================================================
# WEEKLY BORG INTEGRITY TOGGLE
# =============================================================================


@admin_router.get(
    "/admin/item/backups/integrity",
    tags=[tag],
    response_model=BackupIntegrityResponse,
    summary="Get weekly borg integrity check toggle",
    description=(
        "Return the saved weekly-borg-integrity toggle. Off by default; "
        "backupninja containers poll this live before each saturday run."
    ),
    responses={500: {"model": ErrorResponse}},
)
async def admin_backup_integrity_get(request: Request):
    try:
        return JSONResponse(
            content=BackupIntegrityResponse(
                integrity_enabled=await asyncio.to_thread(
                    AdminBackupsService.get_integrity_enabled
                )
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to read integrity toggle",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/item/backups/integrity",
    tags=[tag],
    response_model=BackupIntegrityResponse,
    summary="Enable or disable weekly borg integrity check",
    description=(
        "Persist the weekly-borg-integrity toggle. Takes effect on the next "
        "scheduled run; no container restart required."
    ),
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_backup_integrity_set(
    request: Request,
    data: BackupIntegritySetRequest,
):
    try:
        result = await asyncio.to_thread(
            AdminBackupsService.set_integrity_enabled, data.integrity_enabled
        )
        return JSONResponse(
            content=BackupIntegrityResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to set integrity toggle",
            traceback.format_exc(),
        )


# NOTE: /admin/item/backups/config MUST be declared before
# /admin/item/backups/{backup_id} — otherwise the catch-all matches
# "config" as the backup_id.
@admin_router.get(
    "/admin/item/backups/config",
    tags=[tag],
    response_model=BackupConfigResponse,
    summary="Get backup configuration",
    description="Get backup configuration from environment variables.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_backup_config(request: Request):
    try:
        result = await asyncio.to_thread(AdminBackupsService.get_backup_config)
        return JSONResponse(
            content=BackupConfigResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get backup config",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/item/backups/{backup_id}",
    tags=[tag],
    response_model=BackupItem,
    summary="Get a specific backup",
    description="Get a specific backup by its ID.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_backup_get(
    request: Request,
    backup_id: str = Path(..., description="Backup ID"),
):
    try:
        result = await asyncio.to_thread(AdminBackupsService.get_backup, backup_id)
        return JSONResponse(
            content=BackupItem(**(result or {})).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get backup",
            traceback.format_exc(),
        )


# =============================================================================
# BACKUP REPORT
# =============================================================================


@admin_router.post(
    "/admin/item/backups",
    tags=[tag],
    response_model=BackupReportInsertResponse,
    summary="Submit backup report",
    description=(
        "Ingestion endpoint for backupninja. Rejects non-service callers so "
        "regular admin users cannot forge or pollute backup history."
    ),
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_backup_report(
    request: Request,
    data: BackupReportRequest,
):
    try:
        # Service-token gate: admin_router already filters role=admin, but
        # backup ingestion must be additionally restricted to internal
        # services so an admin user cannot forge or pollute backup history.
        if request.token_payload.get("session_id") != "isardvdi-service":
            raise Error("forbidden", "Service token required.")
        result = await asyncio.to_thread(
            AdminBackupsService.insert_backup, data.model_dump(exclude_none=True)
        )
        return JSONResponse(
            content=BackupReportInsertResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to ingest backup report",
            traceback.format_exc(),
        )
