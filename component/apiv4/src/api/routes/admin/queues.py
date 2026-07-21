#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import time
import traceback
from typing import Literal, Optional

from api import admin_router
from api.schemas.admin.queues import (
    AutoDeleteConfigResponse,
    AutoDeleteEnabledRequest,
    AutoDeleteEnabledResponse,
    AutoDeleteMaxTimeResponse,
    AutoDeleteQueueRegistriesResponse,
    BacklogRollupRow,
    DeleteOldTasksRequest,
    DeleteOldTasksResult,
    GovernorGaugesResponse,
    ProblemTasksResponse,
    QueueConsumerResponse,
    QueueJobsResponse,
    QueueRegistriesRequest,
    StorageSchedulerConfigRequest,
    StorageSchedulerConfigResponse,
)
from api.schemas.common import ErrorResponse
from api.services.admin.queues import AdminQueuesService
from api.services.error import Error
from fastapi import Query, Request
from fastapi.responses import JSONResponse

tag = "admin_queues"


# =============================================================================
# QUEUE ENDPOINTS (admin_router)
# =============================================================================


@admin_router.get(
    "/admin/items/queues",
    tags=[tag],
    response_model=list[QueueJobsResponse],
    summary="List all queues with job counts",
    description="Returns all queues with their job counts by status.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_queues_jobs(request: Request):
    try:
        data = await asyncio.to_thread(AdminQueuesService.get_queues)
        return JSONResponse(
            content=[
                QueueJobsResponse(**row).model_dump(mode="json") for row in (data or [])
            ],
            status_code=200,
        )
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
    "/admin/items/queues/consumers",
    tags=[tag],
    response_model=list[QueueConsumerResponse],
    summary="List queue consumers/workers",
    description="Returns all queue workers with their subscriber information.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_queues_consumers(request: Request):
    try:
        data = await asyncio.to_thread(AdminQueuesService.get_consumers)
        return JSONResponse(
            content=[
                QueueConsumerResponse(**row).model_dump(mode="json")
                for row in (data or [])
            ],
            status_code=200,
        )
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
    "/admin/items/queues/governor",
    tags=[tag],
    response_model=GovernorGaugesResponse,
    response_model_exclude_none=True,
    summary="Storage-governor gauge document",
    description=(
        "Composite storage-governor observability gauges: heavy at-cap + leak, "
        "per-pool/per-category inflight-vs-cap, worker heartbeat health, Redis "
        "health, mode, warnings, effective config, generated_at and truncation "
        "honesty fields. Degrades to a 200 body with honesty fields (redis.up "
        "false, multitenancy_active 'unknown', empty pools/workers) on transient "
        "Redis/rdb failure rather than 5xx — a polled 500 would eject the "
        "operator mid-incident. Also the stats-go scrape source."
    ),
    responses={500: {"model": ErrorResponse}},
)
async def admin_queues_governor(request: Request):
    try:
        data = await asyncio.to_thread(AdminQueuesService.get_governor)
        # Recompute data_age_seconds at response time so a warm 5s cache serve
        # reports its true age (catalog #17 — frozen-cache honesty), not 0.
        generated_at = (data or {}).get("generated_at", time.time())
        data = {
            **(data or {}),
            "data_age_seconds": max(0.0, time.time() - generated_at),
        }
        return GovernorGaugesResponse(**data)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get storage governor gauges",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/items/queues/backlog",
    tags=[tag],
    response_model=list[BacklogRollupRow],
    summary="Per-(pool, category, tier) backlog rollup",
    description=(
        "Per-lane backlog rollup: queued / started / started-over-timeout / "
        "failed / deferred counts, head-only oldest-queued-age, and "
        "has_consumer / coverage_known / stranded coverage flags. Degrades to an "
        "empty list on transient Redis failure rather than 5xx."
    ),
    responses={500: {"model": ErrorResponse}},
)
async def admin_queues_backlog(request: Request):
    try:
        data = await asyncio.to_thread(AdminQueuesService.get_backlog_rollup)
        return [BacklogRollupRow(**row) for row in (data or [])]
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get backlog rollup",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/items/queues/tasks/problems",
    tags=[tag],
    response_model=ProblemTasksResponse,
    response_model_exclude_none=True,
    summary="Bounded, filterable problem-task listing",
    description=(
        "Lists problem tasks — ``failed`` (with traceback + retries_left), "
        "``stuck_running`` (started jobs past their timeout), "
        "``deferred_orphan`` (finalize-crashed deferred jobs whose chain has "
        "settled), or ``all`` — filterable by pool / category_id / tier and "
        "paginated. Every enumeration is bounded (one rq:queues snapshot, per-"
        "lane registry slice with cleanup=False, overall scan cap) and "
        "dangling-safe. Degrades to a 200 body with count 0 / empty tasks on "
        "transient Redis failure rather than 5xx."
    ),
    responses={500: {"model": ErrorResponse}},
)
async def admin_queues_problem_tasks(
    request: Request,
    kind: Literal["failed", "deferred_orphan", "stuck_running", "all"] = "all",
    pool: Optional[str] = None,
    category_id: Optional[str] = None,
    tier: Optional[
        Literal["interactive", "standard", "template", "bulk", "maintenance", "reclaim"]
    ] = None,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
):
    try:
        data = await asyncio.to_thread(
            AdminQueuesService.list_problem_tasks,
            kind,
            pool,
            category_id,
            tier,
            limit,
            offset,
        )
        return ProblemTasksResponse(**data)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list problem tasks",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/item/queues/old_tasks/config",
    tags=[tag],
    response_model=AutoDeleteConfigResponse,
    summary="Get auto delete config",
    description="Returns the auto-delete configuration for old tasks.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_get_old_tasks_config(request: Request):
    try:
        result = await asyncio.to_thread(AdminQueuesService.get_auto_delete_config)
        return JSONResponse(
            content=AutoDeleteConfigResponse(**(result or {})).model_dump(mode="json"),
            status_code=200,
        )
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
    "/admin/items/queues/old_tasks/{older_than}",
    tags=[tag],
    response_model=list[str],
    summary="Get old tasks",
    description="Returns old tasks that are older than the specified seconds.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_old_tasks(request: Request, older_than: int):
    try:
        result = await asyncio.to_thread(AdminQueuesService.get_old_tasks, older_than)
        return JSONResponse(content=result or [], status_code=200)
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
    "/admin/items/queues/old_tasks",
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
        result = await asyncio.to_thread(
            AdminQueuesService.delete_old_tasks, data.older_than
        )
        return JSONResponse(
            content=DeleteOldTasksResult(**(result or {})).model_dump(mode="json"),
            status_code=200,
        )
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
    "/admin/item/queues/old_tasks/config/max_time/{max_time}",
    tags=[tag],
    response_model=AutoDeleteMaxTimeResponse,
    summary="Set auto delete max time",
    description="Sets the maximum time (in seconds, min 86400) for auto-deleting old tasks.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_set_old_tasks_max_time(request: Request, max_time: int):
    try:
        result = await asyncio.to_thread(AdminQueuesService.set_max_time, max_time)
        return JSONResponse(
            content=AutoDeleteMaxTimeResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to set old tasks max time",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/item/queues/storage_scheduler/config",
    tags=[tag],
    response_model=StorageSchedulerConfigResponse,
    summary="Get storage governor config",
    description="Returns the live storage-governor knobs (enabled kill-switch, PSI limit, heavy cap, poll backoff) and the per-category fairness knobs (weights, per-category and default in-flight caps) the elastic storage workers apply.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_get_storage_scheduler_config(request: Request):
    try:
        result = await asyncio.to_thread(
            AdminQueuesService.get_storage_scheduler_config
        )
        return JSONResponse(
            content=StorageSchedulerConfigResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get storage scheduler config",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/item/queues/storage_scheduler/config",
    tags=[tag],
    response_model=StorageSchedulerConfigResponse,
    summary="Set storage governor config",
    description="Live-updates the storage-governor knobs including the per-category fairness weights/caps (partial; only provided keys are written, a supplied category map replaces the stored one). Elastic workers pick up the change within one poll, no restart.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_set_storage_scheduler_config(
    request: Request,
    data: StorageSchedulerConfigRequest,
):
    try:
        result = await asyncio.to_thread(
            AdminQueuesService.set_storage_scheduler_config,
            data.model_dump(exclude_none=True),
        )
        return JSONResponse(
            content=StorageSchedulerConfigResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to set storage scheduler config",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/item/queues/old_tasks/config/queue_registries",
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
):
    try:
        result = await asyncio.to_thread(
            AdminQueuesService.set_queue_registries, data.queue_registries or []
        )
        return JSONResponse(
            content=AutoDeleteQueueRegistriesResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
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
    "/admin/item/queues/old_tasks/config/enabled",
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
):
    try:
        result = await asyncio.to_thread(
            AdminQueuesService.set_auto_delete_enabled, data.enabled
        )
        return JSONResponse(
            content=AutoDeleteEnabledResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
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
    "/admin/items/queues/old_tasks/auto",
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
        result = await asyncio.to_thread(AdminQueuesService.delete_old_tasks_auto)
        return JSONResponse(
            content=DeleteOldTasksResult(**(result or {})).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to auto delete old tasks",
            traceback.format_exc(),
        )
