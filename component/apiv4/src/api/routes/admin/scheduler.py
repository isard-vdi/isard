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

from api import admin_router
from api.schemas.admin.scheduler import SchedulerBookingsJob, SchedulerSystemJob
from api.schemas.common import ErrorResponse
from api.services.admin.scheduler import AdminSchedulerService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse

tag = "admin_scheduler"


@admin_router.get(
    "/admin/items/scheduler/jobs/system",
    tags=[tag],
    response_model=list[SchedulerSystemJob],
    summary="Get system scheduler jobs",
    description="Get the list of system scheduler jobs ordered by next run time.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_scheduler_jobs_system(request: Request):
    try:
        result = await asyncio.to_thread(AdminSchedulerService.get_system_jobs)
        return JSONResponse(
            content=[
                SchedulerSystemJob(**row).model_dump(mode="json") for row in result
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get system scheduler jobs",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/items/scheduler/jobs/bookings",
    tags=[tag],
    response_model=list[SchedulerBookingsJob],
    summary="Get bookings scheduler jobs",
    description="Get the list of bookings scheduler jobs ordered by next run time.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_scheduler_jobs_bookings(
    request: Request,
):
    try:
        result = await asyncio.to_thread(AdminSchedulerService.get_bookings_jobs)
        return JSONResponse(
            content=[
                SchedulerBookingsJob(**row).model_dump(mode="json") for row in result
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get bookings scheduler jobs",
            traceback.format_exc(),
        )
