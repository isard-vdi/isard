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
from datetime import datetime
from typing import Optional

from api import manager_router
from api.dependencies.jwt_token import can_manage_gpu_plannings
from api.schemas.common import DeleteResponse, ErrorResponse, SimpleResponse
from api.schemas.planning import (
    CreatePlanningRequest,
    PlanningDeleteResponse,
    PlanningListResponse,
)
from api.services.error import Error
from api.services.planning import PlanningService
from api.services.reservables import ReservableService
from fastapi import Depends, Path, Query, Request
from fastapi.responses import JSONResponse

tag = "planning"


@manager_router.get(
    "/items/planning/{reservable_item_id}",
    dependencies=[Depends(can_manage_gpu_plannings)],
    response_model=PlanningListResponse,
    tags=[tag],
    summary="Get plannings for a specific reservable item",
    description="Returns all plannings for a specific reservable item, optionally filtered by date range. \nIf no date range is provided, returns ongoing plannings.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_item_plannings(
    request: Request,
    reservable_item_id: str,
    start: Optional[datetime] = Query(
        None,
        description="Start date filter (ISO format, e.g. 2023-10-01T00:00:00+00:00)",
    ),
    end: Optional[datetime] = Query(
        None, description="End date filter (ISO format, e.g. 2023-10-01T00:00:00+00:00)"
    ),
):
    """
    Get plannings for a specific reservable item.
    """

    if not await asyncio.to_thread(
        ReservableService.reservable_item_exists, reservable_item_id
    ):
        raise Error(
            "not_found",
            f"Reservable item '{reservable_item_id}' not found",
            description_code="reservable_item_not_found",
        )

    try:
        plannings = await asyncio.to_thread(
            PlanningService.get_item_plannings,
            request.token_payload,
            reservable_item_id,
            start,
            end,
        )
        return PlanningListResponse(plannings=plannings)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve plannings for item {reservable_item_id}",
            traceback.format_exc(),
        )


@manager_router.delete(
    "/item/planning/{plan_id}",
    dependencies=[Depends(can_manage_gpu_plannings)],
    tags=[tag],
    response_model=DeleteResponse,
    status_code=200,
    summary="Delete a specific planning",
    description="Deletes a specific planning by its ID.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_planning(
    request: Request,
    plan_id: str = Path(..., description="The planning ID to delete"),
):
    """
    Delete a specific planning by its ID.
    """
    try:
        await asyncio.to_thread(
            PlanningService.delete_planning, request.token_payload, plan_id
        )
        return DeleteResponse(message="Planning deleted", message_code="item.deleted")
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to delete planning {plan_id}",
            traceback.format_exc(),
        )


@manager_router.post(
    "/item/planning",
    dependencies=[Depends(can_manage_gpu_plannings)],
    tags=[tag],
    response_model=SimpleResponse,
    summary="Create a new planning",
    description="Creates a new planning for a reservable resource.",
    status_code=201,
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_planning(
    request: Request,
    planning_data: CreatePlanningRequest,
):
    """
    Create a new planning for a reservable resource.
    """
    try:
        plan_id = await asyncio.to_thread(
            PlanningService.create_planning,
            request.token_payload,
            planning_data.model_dump(),
        )
        return SimpleResponse(id=plan_id)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to create planning",
            traceback.format_exc(),
        )
