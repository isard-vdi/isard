# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import traceback

from api import token_router
from api.schemas.common import ErrorResponse
from api.schemas.storage_problems import (
    DesktopStorageProblemsResponse,
    FixName,
    StorageFixResponse,
)
from api.services.error import Error
from api.services.storage_problems import StorageProblemsService
from fastapi import Request
from fastapi.responses import JSONResponse

tag = "storage"


async def _report(request: Request, method, *args, message: str, model):
    try:
        result = await asyncio.to_thread(method, request.token_payload, *args)
        return JSONResponse(
            content=model(**result).model_dump(mode="json"), status_code=200
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request, "internal_server", message, traceback.format_exc()
        )


@token_router.get(
    "/item/desktop/{desktop_id}/storage-problems",
    tags=[tag],
    response_model=DesktopStorageProblemsResponse,
    summary="Storage problems of a desktop",
    description=(
        "Every disk of the desktop with its problems. Each problem says how it is "
        "handled: wait for the task that holds the disk, a quick fix, a costly fix "
        "or an administrator's decision, and whether the caller may run its fix."
    ),
    responses={403: {"model": ErrorResponse}, 404: {"model": ErrorResponse}},
)
async def get_desktop_storage_problems(request: Request, desktop_id: str):
    return await _report(
        request,
        StorageProblemsService.report,
        desktop_id,
        message="Failed to get the storage problems of the desktop",
        model=DesktopStorageProblemsResponse,
    )


@token_router.put(
    "/item/desktop/{desktop_id}/storage-problems",
    tags=[tag],
    response_model=DesktopStorageProblemsResponse,
    summary="Handle the storage problems of a desktop",
    description=(
        "Queues each disk's quick fix at once and records the rest as pending "
        "actions for the storage sweep. Costly repairs are never run here. Refused "
        "with storage_desktop_repairs_disabled unless an administrator turned on "
        "desktop_disk_repairs in the storage sweep config."
    ),
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
    },
)
async def handle_desktop_storage_problems(request: Request, desktop_id: str):
    return await _report(
        request,
        StorageProblemsService.handle,
        desktop_id,
        message="Failed to handle the storage problems of the desktop",
        model=DesktopStorageProblemsResponse,
    )


@token_router.put(
    "/item/desktop/{desktop_id}/storage/{storage_id}/fix/{fix}",
    tags=[tag],
    response_model=StorageFixResponse,
    summary="Run the fix of a desktop's disk",
    description=(
        "Queues one fix a desktop's disk needs. A costly fix (repair_all, "
        "dig_holes, sparsify) is refused with storage_repair_not_allowed unless the "
        "caller is an administrator or matched by the storage repair allowed list. "
        "Refused with storage_fix_not_needed when no problem of the disk calls for "
        "it and storage_fix_in_progress while the disk has a task in progress. A "
        "caller who is not an administrator is refused with "
        "storage_desktop_repairs_disabled while desktop_disk_repairs is off."
    ),
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
    },
)
async def fix_desktop_storage(
    request: Request, desktop_id: str, storage_id: str, fix: FixName
):
    return await _report(
        request,
        StorageProblemsService.fix,
        desktop_id,
        storage_id,
        fix,
        message="Failed to queue the fix of the disk",
        model=StorageFixResponse,
    )
