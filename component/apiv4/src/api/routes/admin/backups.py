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

import traceback

from api import admin_router
from api.schemas.admin_backups import BackupReportRequest
from api.schemas.common import ErrorResponse
from api.services.admin_backups import AdminBackupsService
from api.services.error import Error
from fastapi import Path, Request
from fastapi.responses import JSONResponse

tag = "admin_backups"


# =============================================================================
# BACKUP LISTING
# =============================================================================


@admin_router.get(
    "/admin/backups",
    tags=[tag],
    summary="List backups",
    description=(
        "Get a list of backups. Optionally get a specific backup by ID via "
        "query parameter, or filter by host and limit via query parameters."
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
            result = AdminBackupsService.get_backup(
                options["id"], pluck=options.get("pluck")
            )
        else:
            limit = options.get("limit")
            try:
                limit = int(limit) if limit else None
            except (TypeError, ValueError):
                raise Error("bad_request", "limit must be an integer")
            result = AdminBackupsService.list_backups(
                host=options.get("host"), limit=limit
            )
        return JSONResponse(content=result, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list backups",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/backups/hosts",
    tags=[tag],
    summary="List backup hosts",
    description="Distinct list of hosts that have ever reported a backup.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_backup_hosts(request: Request):
    try:
        result = AdminBackupsService.list_hosts()
        return JSONResponse(content=result, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list backup hosts",
            traceback.format_exc(),
        )


# NOTE: /admin/backups/config MUST be declared before /admin/backups/{backup_id}
# — otherwise the catch-all matches "config" as the backup_id.
@admin_router.get(
    "/admin/backups/config",
    tags=[tag],
    summary="Get backup configuration",
    description="Get backup configuration from environment variables.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_backup_config(request: Request):
    try:
        result = AdminBackupsService.get_backup_config()
        return JSONResponse(content=result, status_code=200)
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
    "/admin/backups/{backup_id}",
    tags=[tag],
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
        result = AdminBackupsService.get_backup(backup_id)
        return JSONResponse(content=result, status_code=200)
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
    "/backups",
    tags=[tag],
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
        result = AdminBackupsService.insert_backup(data.model_dump(exclude_none=True))
        return JSONResponse(content=result, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to ingest backup report",
            traceback.format_exc(),
        )
