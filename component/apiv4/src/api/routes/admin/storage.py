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
from typing import Optional

from api import admin_router, manager_router
from api.schemas.admin.storage import (
    AdminStorageDomain,
    AdminStorageFilterRequest,
    AdminStorageInfo,
    AdminStorageItem,
    AdminStorageStatusCount,
)
from api.schemas.common import DeleteResponse, EmptyResponse, ErrorResponse
from api.services.admin.storage import AdminStorageService
from api.services.error import Error
from fastapi import Path, Request
from fastapi.responses import JSONResponse, Response

tag = "admin_storage"


# =============================================================================
# STORAGE STATUS
# =============================================================================


@manager_router.get(
    "/admin/item/storage/status",
    tags=[tag],
    response_model=list[AdminStorageStatusCount],
    summary="Get storage status counts",
    description="Get counts of storages grouped by status. "
    "Managers are scoped to their category.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_storage_status(request: Request):
    try:
        result = await asyncio.to_thread(
            AdminStorageService.get_storage_status, request.token_payload
        )
        return JSONResponse(
            content=[
                AdminStorageStatusCount(**row).model_dump(mode="json")
                for row in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get storage status",
            traceback.format_exc(),
        )


# =============================================================================
# STORAGE LISTING
# =============================================================================


@manager_router.get(
    "/admin/items/storage",
    tags=[tag],
    response_model=list[AdminStorageItem],
    summary="Get all storages",
    description="Get all storage items. Admins see all; managers are scoped to their category.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_storage_list(request: Request):
    try:
        result = await asyncio.to_thread(
            AdminStorageService.get_storages, request.token_payload
        )
        return JSONResponse(
            content=[
                AdminStorageItem(**row).model_dump(mode="json")
                for row in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get storages",
            traceback.format_exc(),
        )


@manager_router.post(
    "/admin/items/storage",
    tags=[tag],
    response_model=list[AdminStorageItem],
    summary="Get all storages with category filter",
    description="Get all storage items with optional category filter. "
    "Admins can filter by categories; managers are scoped to their category.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_storage_list_filtered(
    request: Request,
    data: AdminStorageFilterRequest,
):
    try:
        result = await asyncio.to_thread(
            AdminStorageService.get_storages,
            request.token_payload,
            categories=data.categories,
        )
        return JSONResponse(
            content=[
                AdminStorageItem(**row).model_dump(mode="json")
                for row in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get storages",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/items/storage/by-status/{status}",
    tags=[tag],
    response_model=list[AdminStorageItem],
    summary="Get storages by status",
    description="Get storage items filtered by status. "
    "Admins see all; managers are scoped to their category.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_storage_by_status(
    request: Request,
    status: str = Path(..., description="Storage status to filter by"),
):
    try:
        result = await asyncio.to_thread(
            AdminStorageService.get_storages, request.token_payload, status=status
        )
        return JSONResponse(
            content=[
                AdminStorageItem(**row).model_dump(mode="json")
                for row in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get storages by status",
            traceback.format_exc(),
        )


@manager_router.post(
    "/admin/items/storage/by-status/{status}",
    tags=[tag],
    response_model=list[AdminStorageItem],
    summary="Get storages by status with category filter",
    description="Get storage items filtered by status with optional category filter.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_storage_by_status_filtered(
    request: Request,
    data: AdminStorageFilterRequest,
    status: str = Path(..., description="Storage status to filter by"),
):
    try:
        result = await asyncio.to_thread(
            AdminStorageService.get_storages,
            request.token_payload,
            status=status,
            categories=data.categories,
        )
        return JSONResponse(
            content=[
                AdminStorageItem(**row).model_dump(mode="json")
                for row in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get storages by status",
            traceback.format_exc(),
        )


# =============================================================================
# STORAGE DOMAINS
# =============================================================================


@manager_router.get(
    "/admin/items/storage/domains/{storage_id:path}",
    tags=[tag],
    response_model=list[AdminStorageDomain],
    summary="Get domains attached to a storage",
    description="Get the list of domains that use a specific storage.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_storage_domains(
    request: Request,
    storage_id: str = Path(..., description="Storage ID"),
):
    try:
        result = await asyncio.to_thread(
            AdminStorageService.get_storage_domains, request.token_payload, storage_id
        )
        return JSONResponse(
            content=[
                AdminStorageDomain(**row).model_dump(mode="json")
                for row in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get storage domains",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/items/media/domains/{storage_id:path}",
    tags=[tag],
    response_model=list[AdminStorageDomain],
    summary="Get domains using a media item",
    description="Get the list of domains that use a specific media item.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_media_domains(
    request: Request,
    storage_id: str = Path(..., description="Media ID"),
):
    try:
        result = await asyncio.to_thread(
            AdminStorageService.get_media_domains, request.token_payload, storage_id
        )
        return JSONResponse(
            content=[
                AdminStorageDomain(**row).model_dump(mode="json")
                for row in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get media domains",
            traceback.format_exc(),
        )


# =============================================================================
# STORAGE CRUD
# =============================================================================


@manager_router.delete(
    "/admin/item/storage/{storage_id}",
    tags=[tag],
    response_model=DeleteResponse,
    status_code=202,
    summary="Delete a storage",
    description=(
        "Delete a storage via the canonical task chain — same chain the "
        "user-facing ``DELETE /item/storage/{id}`` invokes. Rejects with 428 "
        "if the storage still has child storages."
    ),
    responses={
        202: {"model": DeleteResponse},
        404: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_storage_delete(
    request: Request,
    storage_id: str = Path(..., description="Storage ID to delete"),
):
    try:
        task_id = await asyncio.to_thread(
            AdminStorageService.delete_storage,
            request.token_payload,
            storage_id,
        )
        return JSONResponse(
            content=DeleteResponse(
                message="Task to delete storage queued",
                message_code="item.queued",
                tasks_ids=[task_id] if isinstance(task_id, str) else None,
            ).model_dump(mode="json"),
            status_code=202,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete storage",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/item/storage/info/{storage_id}",
    tags=[tag],
    response_model=AdminStorageInfo,
    summary="Get storage information",
    description="Get detailed information about a specific storage.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_storage_info(
    request: Request,
    storage_id: str = Path(..., description="Storage ID"),
):
    try:
        result = await asyncio.to_thread(
            AdminStorageService.get_storage_info, request.token_payload, storage_id
        )
        return JSONResponse(
            content=AdminStorageInfo(**(result or {})).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get storage info",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/item/storage/search-info/{storage_id}",
    tags=[tag],
    response_model=AdminStorageInfo,
    summary="Get storage search information with owner data",
    description="Get storage information including owner details.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_storage_search_info(
    request: Request,
    storage_id: str = Path(..., description="Storage ID"),
):
    try:
        result = await asyncio.to_thread(
            AdminStorageService.get_storage_search_info,
            request.token_payload,
            storage_id,
        )
        return JSONResponse(
            content=AdminStorageInfo(**(result or {})).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get storage search info",
            traceback.format_exc(),
        )


# =============================================================================
# STORAGE BY ROLE (admin only)
# =============================================================================


@admin_router.get(
    "/admin/items/storage/by-role/{role}",
    tags=[tag],
    response_model=list[AdminStorageItem],
    summary="Get storages by user role",
    description="Get all storages filtered by the owning user's role. Admin only.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_storage_by_role(
    request: Request,
    role: str = Path(..., description="User role to filter by"),
):
    try:
        result = await asyncio.to_thread(AdminStorageService.get_storages_by_role, role)
        return JSONResponse(
            content=[
                AdminStorageItem(**row).model_dump(mode="json")
                for row in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get storages by role",
            traceback.format_exc(),
        )
