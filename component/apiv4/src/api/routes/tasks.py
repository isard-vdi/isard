#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import traceback

from api import admin_router, manager_router, token_router
from api.schemas.common import EmptyResponse, ErrorResponse
from api.schemas.tasks import TaskResponse
from api.services.error import Error
from api.services.tasks import TaskService
from fastapi import Request
from fastapi.responses import JSONResponse

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
async def get_task(request: Request, task_id: str) -> TaskResponse:
    try:
        task = await asyncio.to_thread(
            TaskService.get_task_with_owner_check,
            task_id,
            request.token_payload["user_id"],
            request.token_payload.get("role_id", "user"),
        )
        return TaskResponse(**task.to_dict())
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
    response_model=EmptyResponse,
    summary="Cancel a task",
    description="Cancels a queued task. Only the task owner can cancel it.",
    responses={
        404: {"model": ErrorResponse},
        412: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def cancel_task(request: Request, task_id: str) -> EmptyResponse:
    try:
        await asyncio.to_thread(
            TaskService.cancel_task,
            task_id,
            request.token_payload["user_id"],
            request.token_payload.get("role_id", "user"),
        )
        return EmptyResponse()
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
async def get_user_tasks(request: Request) -> list[TaskResponse]:
    try:
        tasks = await asyncio.to_thread(
            TaskService.get_user_tasks, request.token_payload["user_id"]
        )
        return [TaskResponse(**t) for t in (tasks or [])]
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
    description="Returns all tasks. Admins see all tasks, managers see their category tasks.",
    responses={500: {"model": ErrorResponse}},
)
async def get_admin_tasks(request: Request) -> list[TaskResponse]:
    try:
        tasks = await asyncio.to_thread(
            TaskService.get_admin_tasks,
            request.token_payload["user_id"],
            request.token_payload.get("role_id", "user"),
            request.token_payload.get("category_id"),
        )
        return [TaskResponse(**t) for t in (tasks or [])]
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
    response_model=EmptyResponse,
    summary="Retry a failed task",
    description="Retries a failed task. Admin only.",
    responses={
        404: {"model": ErrorResponse},
        412: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def retry_task(request: Request, task_id: str) -> EmptyResponse:
    try:
        await asyncio.to_thread(TaskService.retry_task, task_id)
        return EmptyResponse()
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
    response_model=EmptyResponse,
    summary="Retry all failed storage tasks",
    description="Retries all failed storage tasks in the background. Admin only.",
    responses={500: {"model": ErrorResponse}},
)
async def retry_all_failed_tasks(request: Request):
    try:
        result = await asyncio.to_thread(TaskService.retry_all_failed_tasks)
        return result
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retry all failed tasks",
            traceback.format_exc(),
        )
