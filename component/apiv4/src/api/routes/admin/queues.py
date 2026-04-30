#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import traceback

from api import admin_router
from api.schemas.admin.queues import (
    AutoDeleteConfigResponse,
    AutoDeleteEnabledRequest,
    AutoDeleteEnabledResponse,
    AutoDeleteMaxTimeResponse,
    AutoDeleteQueueRegistriesResponse,
    DeleteOldTasksRequest,
    DeleteOldTasksResult,
    QueueConsumerResponse,
    QueueJobsResponse,
    QueueRegistriesRequest,
)
from api.schemas.common import ErrorResponse
from api.services.admin.queues import AdminQueuesService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse

tag = "admin_queues"


# =============================================================================
# QUEUE ENDPOINTS (admin_router)
# =============================================================================


@admin_router.get(
    "/admin/queues",
    tags=[tag],
    response_model=list[QueueJobsResponse],
    summary="List all queues with job counts",
    description="Returns all queues with their job counts by status.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_queues_jobs(request: Request) -> list[QueueJobsResponse]:
    try:
        data = AdminQueuesService.get_queues()
        return [QueueJobsResponse(**row) for row in (data or [])]
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list queues",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/queues/consumers",
    tags=[tag],
    response_model=list[QueueConsumerResponse],
    summary="List queue consumers/workers",
    description="Returns all queue workers with their subscriber information.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_queues_consumers(request: Request) -> list[QueueConsumerResponse]:
    try:
        data = AdminQueuesService.get_consumers()
        return [QueueConsumerResponse(**row) for row in (data or [])]
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list queue consumers",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/queues/old_tasks/config",
    tags=[tag],
    response_model=AutoDeleteConfigResponse,
    summary="Get auto delete config",
    description="Returns the auto-delete configuration for old tasks.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_get_old_tasks_config(request: Request):
    try:
        result = AdminQueuesService.get_auto_delete_config()
        return result
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get auto delete config",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/queues/old_tasks/{older_than}",
    tags=[tag],
    response_model=list[str],
    summary="Get old tasks",
    description="Returns old tasks that are older than the specified seconds.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_old_tasks(request: Request, older_than: int) -> list[str]:
    try:
        return AdminQueuesService.get_old_tasks(older_than)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get old tasks",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/queues/old_tasks",
    tags=[tag],
    response_model=DeleteOldTasksResult,
    summary="Delete old tasks",
    description="Deletes old tasks older than the specified seconds.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_delete_old_tasks(request: Request, data: DeleteOldTasksRequest):
    try:
        if not data.older_than:
            raise await Error.create(
                request,
                "bad_request",
                "older_than parameter is required.",
            )
        result = AdminQueuesService.delete_old_tasks(data.older_than)
        return result
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete old tasks",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/queues/old_tasks/config/max_time/{max_time}",
    tags=[tag],
    response_model=AutoDeleteMaxTimeResponse,
    summary="Set auto delete max time",
    description="Sets the maximum time (in seconds, min 86400) for auto-deleting old tasks.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_set_old_tasks_max_time(
    request: Request, max_time: int
) -> AutoDeleteMaxTimeResponse:
    try:
        result = AdminQueuesService.set_max_time(max_time)
        return AutoDeleteMaxTimeResponse(**result)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to set old tasks max time",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/queues/old_tasks/config/queue_registries",
    tags=[tag],
    response_model=AutoDeleteQueueRegistriesResponse,
    summary="Set auto delete queue registries",
    description="Sets which queue registries are included in auto-delete.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_set_old_tasks_queue_registries(
    request: Request,
    data: QueueRegistriesRequest,
) -> AutoDeleteQueueRegistriesResponse:
    try:
        result = AdminQueuesService.set_queue_registries(data.queue_registries or [])
        return AutoDeleteQueueRegistriesResponse(**result)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to set queue registries",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/queues/old_tasks/config/enabled",
    tags=[tag],
    response_model=AutoDeleteEnabledResponse,
    summary="Enable or disable auto delete",
    description="Enables or disables the auto-delete of old tasks.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_set_old_tasks_enabled(
    request: Request,
    data: AutoDeleteEnabledRequest,
) -> AutoDeleteEnabledResponse:
    try:
        result = AdminQueuesService.set_auto_delete_enabled(data.enabled)
        return AutoDeleteEnabledResponse(**result)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to set auto delete enabled",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/queues/old_tasks/auto",
    tags=[tag],
    response_model=DeleteOldTasksResult,
    summary="Auto delete old tasks",
    description="Deletes old tasks based on the auto-delete configuration.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_delete_old_tasks_auto(request: Request):
    try:
        result = AdminQueuesService.delete_old_tasks_auto()
        return result
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to auto delete old tasks",
            traceback.format_exc(),
        )
