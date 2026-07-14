#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import traceback

from api import admin_router, manager_router, token_router
from api.schemas.common import ErrorResponse
from api.schemas.tasks import TaskResponse
from api.services.error import Error
from api.services.tasks import TaskService
from fastapi import Query, Request
from fastapi.responses import JSONResponse, Response

tag = "tasks"


# =============================================================================
# USER TASK ENDPOINTS (token_router)
# =============================================================================


@token_router.get(
    "/task/{task_id}",
    tags=[tag],
    response_model=TaskResponse,
    summary="Get a task",
    description="Returns a task by its ID. Users can only see their own tasks.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_task(request: Request, task_id: str):
    try:
        task = await asyncio.to_thread(
            TaskService.get_task_with_owner_check,
            task_id,
            request.token_payload["user_id"],
            request.token_payload.get("role_id", "user"),
        )
        return JSONResponse(
            content=TaskResponse(**task.to_dict()).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get task",
            traceback.format_exc(),
        )


@token_router.delete(
    "/task/{task_id}",
    tags=[tag],
    status_code=204,
    response_class=Response,
    summary="Cancel a task",
    description="Cancels a queued task. Only the task owner can cancel it.",
    responses={
        404: {"model": ErrorResponse},
        412: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def cancel_task(request: Request, task_id: str):
    try:
        await asyncio.to_thread(
            TaskService.cancel_task,
            task_id,
            request.token_payload["user_id"],
            request.token_payload.get("role_id", "user"),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to cancel task",
            traceback.format_exc(),
        )


@token_router.get(
    "/tasks",
    tags=[tag],
    response_model=list[TaskResponse],
    summary="Get user tasks",
    description="Returns all tasks for the authenticated user.",
    responses={500: {"model": ErrorResponse}},
)
async def get_user_tasks(request: Request):
    try:
        tasks = await asyncio.to_thread(
            TaskService.get_user_tasks, request.token_payload["user_id"]
        )
        return JSONResponse(
            content=[TaskResponse(**t).model_dump(mode="json") for t in (tasks or [])],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get user tasks",
            traceback.format_exc(),
        )


# =============================================================================
# ADMIN/MANAGER TASK ENDPOINTS
# =============================================================================


@manager_router.get(
    "/admin/tasks",
    tags=[tag],
    response_model=list[TaskResponse],
    summary="Get all tasks (admin/manager)",
    description=(
        "Returns admin tasks. Defaults to the most recent ``limit`` "
        "tasks; bump to a higher value to paginate through history. "
        "Bug 38 hardening — unbounded responses were ~12 MB / 32 s "
        "and timed out k6's HTTP client."
    ),
    responses={500: {"model": ErrorResponse}},
)
async def get_admin_tasks(
    request: Request,
    limit: int = Query(
        200,
        ge=1,
        le=10000,
        description="Page size (max 10000 to bound payload).",
    ),
    offset: int = Query(
        0, ge=0, description="Skip the first ``offset`` matching tasks."
    ),
):
    try:
        tasks = await asyncio.to_thread(
            TaskService.get_admin_tasks,
            request.token_payload["user_id"],
            request.token_payload.get("role_id", "user"),
            request.token_payload.get("category_id"),
            limit,
            offset,
        )
        return JSONResponse(
            content=[TaskResponse(**t).model_dump(mode="json") for t in (tasks or [])],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get admin tasks",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/task/{task_id}/retry",
    tags=[tag],
    status_code=204,
    response_class=Response,
    summary="Retry a failed task",
    description="Retries a failed task. Admin only.",
    responses={
        404: {"model": ErrorResponse},
        412: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def retry_task(request: Request, task_id: str):
    try:
        await asyncio.to_thread(TaskService.retry_task, task_id)
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retry task",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/tasks/retry",
    tags=[tag],
    status_code=204,
    response_class=Response,
    summary="Retry all failed storage tasks",
    description="Retries all failed storage tasks in the background. Admin only.",
    responses={500: {"model": ErrorResponse}},
)
async def retry_all_failed_tasks(request: Request):
    try:
        await asyncio.to_thread(TaskService.retry_all_failed_tasks)
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retry all failed tasks",
            traceback.format_exc(),
        )
