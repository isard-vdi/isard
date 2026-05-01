#
#   Copyright © 2025 Naomi Hidalgo Piñar
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

from api import admin_router, advanced_router, manager_router, token_router
from api.schemas.common import (
    DeleteResponse,
    EmptyResponse,
    ErrorResponse,
    SimpleResponse,
)
from api.schemas.storage import (
    StorageBatchIdsRequest,
    StorageConvertRequest,
    StorageConvertResponse,
    StorageCreateRequest,
    StorageCreateResponse,
    StorageDerivativesResponse,
    StorageMaintenanceRequest,
    StorageMoveByPathRequest,
    StoragePathRequest,
    StorageReadyResponse,
    StorageRecreateRequest,
    StorageRsyncToPathRequest,
    StorageRsyncToStoragePoolRequest,
    StorageVirtWinRegRequest,
    TaskIdResponse,
)
from api.services.error import Error
from api.services.storage import StorageService
from fastapi import Request
from fastapi.responses import JSONResponse

tag = "storage"


# ── STATUS MANAGEMENT (admin_router) ──────────────────────────────────


@admin_router.put(
    "/item/storage/{storage_id}/status/maintenance",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Set storage to maintenance status",
    description="Sets a storage item to maintenance status.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def set_storage_maintenance(
    request: Request,
    storage_id: str,
    body: StorageMaintenanceRequest,
):
    try:
        result_id = await asyncio.to_thread(
            StorageService.set_maintenance,
            request.token_payload,
            storage_id,
            body.action,
        )
        return SimpleResponse(id=result_id)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to set storage to maintenance",
            traceback.format_exc(),
        )


@admin_router.put(
    "/item/storage/{storage_id}/status/ready",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Set storage to ready status",
    description="Sets a storage item to ready status.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def set_storage_ready(request: Request, storage_id: str):
    try:
        result_id = await asyncio.to_thread(
            StorageService.set_ready, request.token_payload, storage_id
        )
        return SimpleResponse(id=result_id)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to set storage to ready",
            traceback.format_exc(),
        )


@admin_router.put(
    "/items/storage/status",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Batch check backing chain",
    description="Check backing chain for a batch of storages by their IDs.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def batch_check_backing_chain(
    request: Request,
    body: StorageBatchIdsRequest,
):
    try:
        await asyncio.to_thread(
            StorageService.batch_check_backing_chain, request.token_payload, body.ids
        )
        return EmptyResponse()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to batch check backing chain",
            traceback.format_exc(),
        )


@admin_router.put(
    "/items/storage/status/{status}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Batch check backing chain by status",
    description="Check backing chain for all storages with the given status.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def batch_check_backing_chain_by_status(request: Request, status: str):
    try:
        await asyncio.to_thread(
            StorageService.batch_check_backing_chain_by_status,
            request.token_payload,
            status,
        )
        return EmptyResponse()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to batch check backing chain by status",
            traceback.format_exc(),
        )


# ── CRUD ──────────────────────────────────────────────────────────────


@token_router.get(
    "/item/storage/{storage_id}",
    tags=[tag],
    response_model=dict,
    summary="Get storage details",
    description="Returns details of a storage item.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_storage(request: Request, storage_id: str) -> dict:
    try:
        storage = await asyncio.to_thread(
            StorageService.get_storage_detail, request.token_payload, storage_id
        )
        return storage if isinstance(storage, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve storage",
            traceback.format_exc(),
        )


@token_router.get(
    "/items/storage/ready",
    tags=[tag],
    response_model=list[dict],
    summary="Get user's ready disks",
    description="Returns a list of ready storage items for the authenticated user.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_user_ready_storages(request: Request) -> list[dict]:
    try:
        disks = await asyncio.to_thread(
            StorageService.get_user_ready_storages, request.token_payload["user_id"]
        )
        return disks or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve ready storages",
            traceback.format_exc(),
        )


@admin_router.post(
    "/item/storage/priority/{priority}",
    tags=[tag],
    response_model=StorageCreateResponse,
    summary="Create a new storage",
    description="Creates a new storage with the given specifications.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_storage(
    request: Request,
    priority: str,
    body: StorageCreateRequest,
):
    try:
        result = await asyncio.to_thread(
            StorageService.create_storage,
            payload=request.token_payload,
            usage=body.usage,
            storage_type=body.storage_type,
            parent=body.parent,
            size=body.size,
            user_id=body.user_id,
            priority=priority,
        )
        return StorageCreateResponse(**result)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create storage",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/item/storage/{storage_id}",
    tags=[tag],
    response_model=DeleteResponse,
    status_code=202,
    summary="Delete a storage",
    description="Deletes a storage item and returns the task ID.",
    responses={
        202: {"model": DeleteResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_storage(request: Request, storage_id: str):
    try:
        task_id = await asyncio.to_thread(
            StorageService.delete_storage, request.token_payload, storage_id
        )
        return DeleteResponse(
            message="Task to delete storage queued",
            message_code="item.queued",
            tasks_ids=[task_id] if isinstance(task_id, str) else None,
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


# ── STORAGE INFO ──────────────────────────────────────────────────────


@manager_router.get(
    "/item/storage/{storage_id}/parents",
    tags=[tag],
    response_model=list[dict],
    summary="Get storage parent chain",
    description="Returns the parent chain of a storage item.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_storage_parents(request: Request, storage_id: str) -> list[dict]:
    try:
        parents = await asyncio.to_thread(
            StorageService.get_parents, request.token_payload, storage_id
        )
        return parents or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve storage parents",
            traceback.format_exc(),
        )


@manager_router.get(
    "/item/storage/{storage_id}/task",
    tags=[tag],
    response_model=dict,
    summary="Get storage task",
    description="Returns the task associated with a storage item.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_storage_task(request: Request, storage_id: str) -> dict:
    try:
        task = await asyncio.to_thread(
            StorageService.get_task, request.token_payload, storage_id
        )
        return task if isinstance(task, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve storage task",
            traceback.format_exc(),
        )


@admin_router.get(
    "/item/storage/{storage_id}/statuses",
    tags=[tag],
    response_model=list[dict],
    summary="Get storage and domain statuses",
    description="Returns the status of a storage and its associated domains.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_storage_statuses(request: Request, storage_id: str) -> list[dict]:
    try:
        statuses = await asyncio.to_thread(
            StorageService.get_statuses, request.token_payload, storage_id
        )
        return statuses or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve storage statuses",
            traceback.format_exc(),
        )


@manager_router.get(
    "/item/storage/{storage_id}/has-derivatives",
    tags=[tag],
    response_model=StorageDerivativesResponse,
    summary="Check if storage has derivatives",
    description="Returns the number of derivatives (children) for a storage item.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_storage_has_derivatives(request: Request, storage_id: str):
    try:
        count = await asyncio.to_thread(
            StorageService.has_derivatives, request.token_payload, storage_id
        )
        return StorageDerivativesResponse(derivatives=count)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to check storage derivatives",
            traceback.format_exc(),
        )


# ── DISK OPERATIONS ──────────────────────────────────────────────────


@admin_router.put(
    "/item/storage/{storage_id}/sparsify/priority/{priority}",
    tags=[tag],
    response_model=TaskIdResponse,
    summary="Sparsify a storage",
    description="Creates a task to sparsify a storage qcow2 image.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def sparsify_storage(request: Request, storage_id: str, priority: str):
    try:
        task_id = await asyncio.to_thread(
            StorageService.sparsify, request.token_payload, storage_id, priority
        )
        return TaskIdResponse(task_id=task_id)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to sparsify storage",
            traceback.format_exc(),
        )


@admin_router.put(
    "/items/storage/sparsify",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Batch sparsify storages",
    description="Sparsify multiple storages by their IDs.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def batch_sparsify_storages(
    request: Request,
    body: StorageBatchIdsRequest,
):
    try:
        await asyncio.to_thread(
            StorageService.batch_sparsify, request.token_payload, body.ids
        )
        return EmptyResponse()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to batch sparsify storages",
            traceback.format_exc(),
        )


@admin_router.put(
    "/item/storage/{storage_id}/disconnect/priority/{priority}",
    tags=[tag],
    response_model=TaskIdResponse,
    summary="Disconnect storage from backing chain",
    description="Creates a task to disconnect a storage from its backing chain.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def disconnect_storage(request: Request, storage_id: str, priority: str):
    try:
        task_id = await asyncio.to_thread(
            StorageService.disconnect, request.token_payload, storage_id, priority
        )
        return TaskIdResponse(task_id=task_id)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to disconnect storage",
            traceback.format_exc(),
        )


@manager_router.put(
    "/item/storage/{storage_id}/check-backing-chain",
    tags=[tag],
    response_model=dict,
    summary="Check storage backing chain",
    description="Creates a task to check the backing chain of a storage.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def check_storage_backing_chain(request: Request, storage_id: str) -> dict:
    try:
        result = await asyncio.to_thread(
            StorageService.check_backing_chain, request.token_payload, storage_id
        )
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to check backing chain",
            traceback.format_exc(),
        )


@admin_router.post(
    "/item/storage/{storage_id}/convert",
    tags=[tag],
    response_model=StorageConvertResponse,
    summary="Convert a storage",
    description="Creates a task to convert a storage to a new format.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def convert_storage(
    request: Request,
    storage_id: str,
    body: StorageConvertRequest,
):
    try:
        result = await asyncio.to_thread(
            StorageService.convert,
            payload=request.token_payload,
            storage_id=storage_id,
            new_storage_type=body.new_storage_type,
            new_storage_status=body.new_storage_status,
            compress=body.compress,
            priority=body.priority,
        )
        return StorageConvertResponse(**result)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to convert storage",
            traceback.format_exc(),
        )


@manager_router.post(
    "/item/storage/{storage_id}/recreate",
    tags=[tag],
    response_model=TaskIdResponse,
    summary="Recreate a storage",
    description="Recreates a storage with the same specifications and parent.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def recreate_storage(
    request: Request,
    storage_id: str,
    body: StorageRecreateRequest,
):
    try:
        task_id = await asyncio.to_thread(
            StorageService.recreate,
            payload=request.token_payload,
            storage_id=storage_id,
            priority=body.priority,
            retry=body.retry,
        )
        return TaskIdResponse(task_id=task_id)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to recreate storage",
            traceback.format_exc(),
        )


@admin_router.put(
    "/item/storage/{storage_id}/virt-win-reg/priority/{priority}",
    tags=[tag],
    response_model=TaskIdResponse,
    summary="Apply Windows registry patch",
    description="Applies a registry patch to a storage qcow2 image.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def virt_win_reg_storage(
    request: Request,
    storage_id: str,
    priority: str,
    body: StorageVirtWinRegRequest,
):
    try:
        task_id = await asyncio.to_thread(
            StorageService.virt_win_reg,
            payload=request.token_payload,
            storage_id=storage_id,
            registry_patch=body.registry_patch,
            priority=priority,
            retry=body.retry,
        )
        return TaskIdResponse(task_id=task_id)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to apply registry patch",
            traceback.format_exc(),
        )


# ── MOVEMENT (admin_router) ──────────────────────────────────────────


@admin_router.put(
    "/item/storage/{storage_id}/move/by-path",
    tags=[tag],
    response_model=TaskIdResponse,
    summary="Move storage by path",
    description="Creates a task to move a storage to a new path.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def move_storage_by_path(
    request: Request,
    storage_id: str,
    body: StorageMoveByPathRequest,
):
    try:
        task_id = await asyncio.to_thread(
            StorageService.move_by_path,
            payload=request.token_payload,
            storage_id=storage_id,
            dest_path=body.dest_path,
            priority=body.priority,
        )
        return TaskIdResponse(task_id=task_id)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to move storage",
            traceback.format_exc(),
        )


@admin_router.put(
    "/item/storage/{storage_id}/rsync/to-path",
    tags=[tag],
    response_model=TaskIdResponse,
    summary="Rsync storage to path",
    description="Creates a task to rsync a storage to a destination path.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def rsync_storage_to_path(
    request: Request,
    storage_id: str,
    body: StorageRsyncToPathRequest,
):
    try:
        task_id = await asyncio.to_thread(
            StorageService.rsync_to_path,
            payload=request.token_payload,
            storage_id=storage_id,
            destination_path=body.destination_path,
            bwlimit=body.bwlimit,
            remove_source_file=body.remove_source_file,
            priority=body.priority,
        )
        return TaskIdResponse(task_id=task_id)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to rsync storage to path",
            traceback.format_exc(),
        )


@admin_router.put(
    "/item/storage/{storage_id}/rsync/to-storage-pool",
    tags=[tag],
    response_model=TaskIdResponse,
    summary="Rsync storage to storage pool",
    description="Creates a task to rsync a storage to a storage pool.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def rsync_storage_to_storage_pool(
    request: Request,
    storage_id: str,
    body: StorageRsyncToStoragePoolRequest,
):
    try:
        task_id = await asyncio.to_thread(
            StorageService.rsync_to_storage_pool,
            payload=request.token_payload,
            storage_id=storage_id,
            destination_storage_pool_id=body.destination_storage_pool_id,
            bwlimit=body.bwlimit,
            remove_source_file=body.remove_source_file,
            priority=body.priority,
        )
        return TaskIdResponse(task_id=task_id)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to rsync storage to storage pool",
            traceback.format_exc(),
        )


# ── MANAGEMENT ────────────────────────────────────────────────────────


@manager_router.put(
    "/item/storage/{storage_id}/stop",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Stop desktops using storage",
    description="Stops all desktops that are using the specified storage.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def stop_storage_desktops(request: Request, storage_id: str):
    try:
        await asyncio.to_thread(
            StorageService.stop_desktops, request.token_payload, storage_id
        )
        return EmptyResponse()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to stop desktops",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/storage/{storage_id}/abort-operations",
    tags=[tag],
    response_model=TaskIdResponse,
    summary="Abort storage operations",
    description="Aborts ongoing operations for a storage item.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def abort_storage_operations(request: Request, storage_id: str):
    try:
        task_id = await asyncio.to_thread(
            StorageService.abort_operations, request.token_payload, storage_id
        )
        return TaskIdResponse(task_id=task_id)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to abort storage operations",
            traceback.format_exc(),
        )


@admin_router.put(
    "/item/storage/{storage_id}/path",
    tags=[tag],
    response_model=TaskIdResponse,
    summary="Set storage path",
    description="Sets the path for a storage item.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def set_storage_path(
    request: Request,
    storage_id: str,
    body: StoragePathRequest,
):
    try:
        task_id = await asyncio.to_thread(
            StorageService.set_path,
            payload=request.token_payload,
            storage_id=storage_id,
            path=body.path,
            priority=body.priority,
            retry=body.retry,
        )
        return TaskIdResponse(task_id=task_id)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to set storage path",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/item/storage/{storage_id}/path",
    tags=[tag],
    response_model=TaskIdResponse,
    summary="Delete storage path",
    description="Deletes the path for a storage item.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_storage_path(
    request: Request,
    storage_id: str,
    body: StoragePathRequest,
):
    try:
        task_id = await asyncio.to_thread(
            StorageService.delete_path,
            payload=request.token_payload,
            storage_id=storage_id,
            path=body.path,
            priority=body.priority,
            retry=body.retry,
        )
        return TaskIdResponse(task_id=task_id)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete storage path",
            traceback.format_exc(),
        )


# ── DISCOVERY (admin_router) ─────────────────────────────────────────


@admin_router.get(
    "/item/storage/{storage_id}/find",
    tags=[tag],
    response_model=dict,
    summary="Find a storage on disk",
    description="Finds a storage item on disk and returns its information.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def find_storage(request: Request, storage_id: str) -> dict:
    try:
        result = await asyncio.to_thread(
            StorageService.find, request.token_payload, storage_id
        )
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to find storage",
            traceback.format_exc(),
        )


@admin_router.put(
    "/items/storage/find",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Batch find storages",
    description="Finds multiple storages on disk by their IDs.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def batch_find_storages(
    request: Request,
    body: StorageBatchIdsRequest,
):
    try:
        await asyncio.to_thread(
            StorageService.batch_find, request.token_payload, body.ids
        )
        return EmptyResponse()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to batch find storages",
            traceback.format_exc(),
        )


# ── EXISTING ENDPOINTS (preserved) ───────────────────────────────────


@token_router.get(
    "/items/storage/get-ready",
    tags=[tag],
    response_model=StorageReadyResponse,
    summary="Get ready storage items",
    description=(
        "Returns the list of storage items in the ``ready`` state that "
        "belong to the calling user. ``@has_token``."
    ),
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_storage_ready(request: Request):
    try:
        items = await asyncio.to_thread(
            StorageService.get_user_ready_storages, request.token_payload["user_id"]
        )
        return StorageReadyResponse(items=items)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve ready storage items",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/item/storage/{storage_id}/priority/{priority}/increase/{increment}",
    tags=[tag],
    response_model=TaskIdResponse,
    summary="Increase storage size",
    description=(
        "Schedules a task to increase a storage's virtual size by "
        "``{increment}`` GB. ``@is_not_user``."
    ),
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def increase_storage_size(
    request: Request,
    storage_id: str,
    priority: str,
    increment: int,
):
    try:
        task_id = await asyncio.to_thread(
            StorageService.increase_size,
            payload=request.token_payload,
            storage_id=storage_id,
            increment=increment,
            priority=priority,
        )
        return TaskIdResponse(task_id=task_id)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to increase storage size",
            traceback.format_exc(),
        )


# ── storages_with_uuid (admin storage diagnostics) ──────────────────────


@manager_router.get(
    "/item/storage/{storage_id}/storages_with_uuid",
    tags=[tag],
    response_model=list[dict],
    summary="Get phantom storages registered against a single storage",
    description=(
        "Returns the ``storages_with_uuid`` field of a single storage. "
        "``@is_admin_or_manager``."
    ),
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_storage_storages_with_uuid(
    request: Request, storage_id: str
) -> list[dict]:
    try:
        result = await asyncio.to_thread(
            StorageService.get_storage_storages_with_uuid,
            request.token_payload,
            storage_id,
        )
        return result or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve storages_with_uuid for storage",
            traceback.format_exc(),
        )


@manager_router.get(
    "/items/storage/storages_with_uuid",
    tags=[tag],
    response_model=list[dict],
    summary="List all storages_with_uuid entries",
    description=(
        "Returns the union of every ``storages_with_uuid`` row in the "
        "storage table. Manager-role callers are scoped to their own "
        "category; admins see everything."
    ),
    responses={500: {"model": ErrorResponse}},
)
async def list_all_storages_with_uuid(request: Request) -> list[dict]:
    try:
        result = await asyncio.to_thread(
            StorageService.get_all_storages_with_uuid, request.token_payload
        )
        return result or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve storages_with_uuid",
            traceback.format_exc(),
        )


@manager_router.get(
    "/items/storage/storages_with_uuid/status",
    tags=[tag],
    response_model=list[dict],
    summary="Get per-status counts of storages_with_uuid",
    description=(
        "Returns the per-status counts of phantom ``storages_with_uuid`` "
        "rows. Manager-role callers are scoped to their own category."
    ),
    responses={500: {"model": ErrorResponse}},
)
async def list_all_storages_with_uuid_status(request: Request) -> list[dict]:
    try:
        result = await asyncio.to_thread(
            StorageService.get_all_storages_with_uuid_status, request.token_payload
        )
        return result or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve storages_with_uuid status counts",
            traceback.format_exc(),
        )


@manager_router.get(
    "/items/storage/storages_with_uuid/{status}",
    tags=[tag],
    response_model=list[dict],
    summary="List storages_with_uuid filtered by status",
    description=(
        "Returns the ``storages_with_uuid`` rows matching the given " "``status``."
    ),
    responses={500: {"model": ErrorResponse}},
)
async def list_all_storages_with_uuid_filtered(
    request: Request, status: str
) -> list[dict]:
    try:
        result = await asyncio.to_thread(
            StorageService.get_all_storages_with_uuid,
            request.token_payload,
            status=status,
        )
        return result or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve storages_with_uuid for status",
            traceback.format_exc(),
        )
