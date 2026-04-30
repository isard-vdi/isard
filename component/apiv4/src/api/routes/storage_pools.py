#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Miriam Melina Gamboa Valdez
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

import traceback

from api import admin_router, manager_router, token_router
from api.dependencies.storage_pools import check_create_storage_pool_availability
from api.schemas.common import EmptyResponse, ErrorResponse
from api.schemas.storage_pools import (
    CheckCategoryAvailabilityRequest,
    CheckCategoryAvailabilityResponse,
    StoragePoolByPathRequest,
    StoragePoolCreateRequest,
    StoragePoolListResponse,
    StoragePoolResponse,
    StoragePoolUpdateRequest,
)
from api.services.error import Error
from api.services.storage_pools import StoragePoolService
from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response

tag = "storage_pools"


# ── Token-level endpoints (any authenticated user) ──────────────────────


@token_router.get(
    "/storage_pools/check-create-availability",
    tags=[tag],
    summary="Check storage pool creation availability",
    description="Checks if there's any storage pool category available for creating a new domain",
    responses={
        204: {"description": "Can create a new storage pool"},
        428: {"model": ErrorResponse},
    },
    dependencies=[Depends(check_create_storage_pool_availability)],
)
async def check_storage_pool_creation_availability():
    return Response(status_code=204)


# ── Manager-level endpoints (manager + admin) ───────────────────────────


@manager_router.get(
    "/storage-pool/default",
    tags=[tag],
    response_model=StoragePoolResponse,
    summary="Get default storage pool",
    description="Returns the default storage pool.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_default_storage_pool(request: Request) -> StoragePoolResponse:
    try:
        result = StoragePoolService.get_default_storage_pool()
        return StoragePoolResponse(**(result or {}))
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve default storage pool",
            traceback.format_exc(),
        )


@manager_router.put(
    "/storage-pool/by-path",
    tags=[tag],
    response_model=StoragePoolResponse,
    summary="Get storage pool by path",
    description="Returns the storage pool that matches the given path.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_storage_pool_by_path(
    request: Request, data: StoragePoolByPathRequest
) -> StoragePoolResponse:
    try:
        storage_pool = StoragePoolService.get_storage_pool_by_path(data.path)
        return StoragePoolResponse(**(storage_pool or {}))
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve storage pool by path",
            traceback.format_exc(),
        )


# ── Admin-level endpoints ────────────────────────────────────────────────


@admin_router.post(
    "/storage-pool",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Create storage pool",
    description="Creates a new storage pool.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def create_storage_pool(request: Request, data: StoragePoolCreateRequest):
    try:
        StoragePoolService.add_storage_pool(data.model_dump(exclude_none=True))
        return EmptyResponse()
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create storage pool",
            traceback.format_exc(),
        )


@admin_router.get(
    "/storage-pools",
    tags=[tag],
    response_model=StoragePoolListResponse,
    summary="List all storage pools",
    description="Returns all storage pools with enriched data.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def list_storage_pools(request: Request):
    try:
        return StoragePoolListResponse(
            storage_pools=StoragePoolService.get_storage_pools()
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve storage pools",
            traceback.format_exc(),
        )


@token_router.get(
    "/storage-pool/availability",
    tags=[tag],
    response_model=CheckCategoryAvailabilityResponse,
    summary="Check storage pool availability",
    description="Check if storage pools are available for the user's category.",
    responses={204: {"description": "Available"}, 500: {"model": ErrorResponse}},
)
async def check_storage_pool_availability_compat(
    request: Request,
) -> CheckCategoryAvailabilityResponse:
    try:
        from api.dependencies.storage_pools import (
            check_create_storage_pool_availability,
        )

        await check_create_storage_pool_availability(request.token_payload)
        return CheckCategoryAvailabilityResponse(available=True)
    except Error:
        raise
    except Exception:
        return CheckCategoryAvailabilityResponse(available=False)


@admin_router.get(
    "/storage-pool/{storage_pool_id}",
    tags=[tag],
    response_model=StoragePoolResponse,
    summary="Get storage pool",
    description="Returns a specific storage pool by ID.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_storage_pool(request: Request, storage_pool_id: str):
    try:
        storage_pool = StoragePoolService.get_storage_pool(storage_pool_id)
        return storage_pool
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve storage pool",
            traceback.format_exc(),
        )


@admin_router.put(
    "/storage-pool/{storage_pool_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update storage pool",
    description="Updates an existing storage pool.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def update_storage_pool(
    request: Request, storage_pool_id: str, data: StoragePoolUpdateRequest
):
    try:
        StoragePoolService.update_storage_pool(
            storage_pool_id, data.model_dump(exclude_none=True)
        )
        return EmptyResponse()
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update storage pool",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/storage-pool/{storage_pool_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete storage pool",
    description="Deletes a storage pool by ID.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def delete_storage_pool(request: Request, storage_pool_id: str):
    try:
        StoragePoolService.delete_storage_pool(storage_pool_id)
        return EmptyResponse()
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete storage pool",
            traceback.format_exc(),
        )


@admin_router.post(
    "/storage-pool/check-category-availability",
    tags=[tag],
    response_model=CheckCategoryAvailabilityResponse,
    summary="Check category availability",
    description="Checks if the given categories are available for assignment to a storage pool.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def check_category_storage_pool_availability(
    request: Request, data: CheckCategoryAvailabilityRequest
):
    try:
        available = StoragePoolService.check_category_availability(
            data.categories, data.storage_pool_id
        )
        return CheckCategoryAvailabilityResponse(available=available)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to check category availability",
            traceback.format_exc(),
        )
