#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import traceback

from api import admin_router
from api.schemas.common import ErrorResponse
from api.services.admin_operations import AdminOperationsService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse

tag = "admin_operations"


# =============================================================================
# OPERATIONS HYPERVISORS (admin_router)
# =============================================================================


@admin_router.get(
    "/admin/operations/hypervisors",
    tags=[tag],
    summary="List operations hypervisors",
    description="Lists all hypervisors managed by the operations service. Requires operations API to be enabled.",
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_operations_hypervisors(request: Request):
    try:
        if not AdminOperationsService.is_operations_api_enabled():
            raise await Error.create(
                request,
                "forbidden",
                "Operations API is not enabled",
            )
        result = AdminOperationsService.list_hypervisors()
        return JSONResponse(content=result, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list operations hypervisors",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/operations/hypervisor/{hypervisor_id}",
    tags=[tag],
    summary="Start a hypervisor",
    description="Starts a hypervisor via the operations service. Requires operations API to be enabled.",
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_operations_hypervisor_start(request: Request, hypervisor_id: str):
    try:
        if not AdminOperationsService.is_operations_api_enabled():
            raise await Error.create(
                request,
                "forbidden",
                "Operations API is not enabled",
            )
        result = AdminOperationsService.start_hypervisor(hypervisor_id)
        return JSONResponse(content=result, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to start hypervisor",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/operations/hypervisor/{hypervisor_id}",
    tags=[tag],
    summary="Stop a hypervisor",
    description="Stops a hypervisor via the operations service. Requires operations API to be enabled.",
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_operations_hypervisor_stop(request: Request, hypervisor_id: str):
    try:
        if not AdminOperationsService.is_operations_api_enabled():
            raise await Error.create(
                request,
                "forbidden",
                "Operations API is not enabled",
            )
        result = AdminOperationsService.stop_hypervisor(hypervisor_id)
        return JSONResponse(content=result, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to stop hypervisor",
            traceback.format_exc(),
        )
