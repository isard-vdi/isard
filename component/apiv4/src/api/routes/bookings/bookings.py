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
import uuid
from datetime import datetime, timedelta, timezone
from typing import Annotated, Literal, Optional

from api import admin_router, advanced_router, open_router, token_router
from api.dependencies.alloweds import (
    owns_booking_id,
    owns_deployment_id,
    owns_domain_id,
)
from api.schemas.bookings import (
    AdminBookingResponse,
    AvailabilityResponse,
    BookingEventResponse,
    BookingPlanResponse,
    BookingPriorityDesktopResponse,
    BookingPriorityUser,
    CreateBookingEventRequest,
    GetUsersPrioritiesRequest,
    GpuForecastProfile,
    ItemBookingsResponse,
    MaxBookingDateResponse,
    PriorityRuleResponse,
    UpdateBookingEventRequest,
    UserBookingResponse,
)
from api.schemas.common import EmptyResponse, ErrorResponse
from api.schemas.reservables import AvailableReservablesResponse
from api.services.bookings import BookingsService
from api.services.error import Error
from fastapi import Depends, Path, Query, Request
from fastapi.responses import JSONResponse
from pydantic import AwareDatetime

tag = "bookings"


@token_router.get(
    "/items/bookings",
    tags=[tag],
    response_model=list[UserBookingResponse],
    summary="Get user bookings",
    description="Returns a list of user bookings.",
)
async def get_user_bookings(
    request: Request,
    start_date: Annotated[
        AwareDatetime | None,
        Query(
            description="Start date in ISO 8601 format. Defaults to now.",
            alias="startDate",
        ),
    ] = None,
    end_date: Annotated[
        AwareDatetime | None,
        Query(
            description="End date in ISO 8601 format. Defaults to 30 days from start.",
            alias="endDate",
        ),
    ] = None,
):
    try:
        if start_date is None:
            start_date = datetime.now(timezone.utc)
        if end_date is None:
            end_date = start_date + timedelta(days=30)
        return [
            UserBookingResponse(**booking)
            for booking in await asyncio.to_thread(
                BookingsService.get_user_bookings,
                start_date,
                end_date,
                request.token_payload,
            )
        ]
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user bookings.",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/booking/get-desktop/{item_id}",
    tags=[tag],
    response_model=ItemBookingsResponse,
    summary="Get desktop's bookings",
    description="Returns the bookings for a specific desktop.",
    operation_id="get_booking_desktop",
    dependencies=[
        Depends(owns_domain_id("item_id")),
    ],
)
@advanced_router.get(
    "/item/booking/get-deployment/{item_id}",
    tags=[tag],
    response_model=ItemBookingsResponse,
    summary="Get deployment's bookings",
    description="Returns the bookings for a specific deployment.",
    operation_id="get_booking_deployment",
    dependencies=[
        Depends(owns_deployment_id("item_id")),
    ],
)
async def get_booking_desktop(
    request: Request,
    item_id: Annotated[
        str, Path(description="The ID of the desktop to retrieve bookings for.")
    ],
    start_date: Annotated[
        AwareDatetime,
        Query(
            description="Start date in ISO 8601 format",
            alias="startDate",
        ),
    ],
    end_date: Annotated[
        AwareDatetime,
        Query(
            description="End date in ISO 8601 format",
            alias="endDate",
        ),
    ],
    return_type: Annotated[
        Literal["all", "event", "availability"],
        Query(
            description="Type of bookings to return: 'all' for all bookings, 'event' for booking events only, 'availability' for availability slots only.",
            alias="returnType",
        ),
    ] = "all",
):
    try:
        match request.url.path.split("/")[-2]:
            case "get-desktop":
                item_type = "desktop"
            case "get-deployment":
                item_type = "deployment"
            case _:
                raise ValueError("Invalid endpoint")

        return ItemBookingsResponse(
            await asyncio.to_thread(
                BookingsService.get_item_bookings,
                request.token_payload,
                start_date,
                end_date,
                item_type,
                item_id,
                return_type,
            )
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user bookings.",
            traceback.format_exc(),
        )


@token_router.get(
    "/items/bookings/get-priority-desktop/{item_id}",
    tags=[tag],
    response_model=BookingPriorityDesktopResponse,
    summary="Get booking priority for a desktop",
    description=(
        "Returns the calling user's booking priority profile and the "
        "desktop name. ``@has_token`` + ``ownsDomainId``."
    ),
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_domain_id("item_id"))],
)
async def get_booking_priority_desktop(request: Request, item_id: str):
    try:
        result = await asyncio.to_thread(
            BookingsService.get_user_priority_for_desktop,
            request.token_payload,
            item_id,
        )
        return BookingPriorityDesktopResponse(**result)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve booking priority for desktop",
            traceback.format_exc(),
        )


@token_router.delete(
    "/item/booking/event/{booking_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete booking event",
    description=(
        "Deletes a booking event. ``@has_token`` + ``ownsBookingId``. "
        "Refuses to delete an in-progress booking while its "
        "desktop/deployment is still running."
    ),
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        428: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_booking_id)],
)
async def delete_booking_event(request: Request, booking_id: str):
    try:
        await asyncio.to_thread(BookingsService.delete_booking_event, booking_id)
        return EmptyResponse()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete booking event",
            traceback.format_exc(),
        )


@token_router.put(
    "/item/booking/event/{booking_id}/edit",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update booking event",
    description=(
        "Edits an existing booking event's title and time window. "
        "``@has_token`` + ``ownsBookingId``."
    ),
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
    dependencies=[Depends(owns_booking_id)],
)
async def update_booking_event(
    request: Request, booking_id: str, booking_data: UpdateBookingEventRequest
):
    try:
        await asyncio.to_thread(
            BookingsService.update_booking_event,
            payload=request.token_payload,
            booking_id=booking_id,
            title=booking_data.title,
            start=booking_data.start.strftime("%Y-%m-%dT%H:%M%z"),
            end=booking_data.end.strftime("%Y-%m-%dT%H:%M%z"),
        )
        return EmptyResponse()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update booking event",
            traceback.format_exc(),
        )


@token_router.post(
    "/item/booking/event",
    tags=[tag],
    response_model=BookingEventResponse,
    status_code=201,
    summary="Create booking event",
    description="Creates a new booking event.",
    responses={
        428: {"model": ErrorResponse},
    },
)
async def create_booking_event(request: Request, new_event: CreateBookingEventRequest):
    try:
        return BookingEventResponse(
            **await asyncio.to_thread(
                BookingsService.create_booking_event, request.token_payload, new_event
            )
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create booking event.",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/booking/max-booking-date/{desktop_id}",
    tags=[tag],
    response_model=MaxBookingDateResponse,
    summary="Get max booking date",
    description="Returns the maximum booking date for a desktop.",
)
async def get_max_booking_date(request: Request, desktop_id: str):
    try:
        return MaxBookingDateResponse(
            max_booking_date=await asyncio.to_thread(
                BookingsService.get_max_booking_date, request.token_payload, desktop_id
            )
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve max booking date.",
            traceback.format_exc(),
        )


@admin_router.get(
    "/items/bookings/all",
    tags=[tag],
    response_model=list[AdminBookingResponse],
    summary="Get all bookings",
    description="Returns a list of all bookings (admin only).",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_all_bookings(request: Request):
    try:
        return [
            AdminBookingResponse(**booking)
            for booking in await asyncio.to_thread(BookingsService.get_all_bookings)
        ]
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve all bookings.",
            traceback.format_exc(),
        )


@admin_router.post(
    "/items/bookings/priorities",
    tags=[tag],
    response_model=list[BookingPriorityUser],
    summary="Get users by priority rule",
    description="Returns users matching a priority rule.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_users_priorities(
    request: Request, data: GetUsersPrioritiesRequest
) -> list[BookingPriorityUser]:
    try:
        result = await asyncio.to_thread(
            BookingsService.get_users_priorities, data.rule_id
        )
        return [BookingPriorityUser(**row) for row in (result or [])]
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve users priorities.",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/item/booking/priority/{priority_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete priority",
    description="Deletes a booking priority by ID.",
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_priority(request: Request, priority_id: str):
    if priority_id in ["default", "default admins"]:
        raise await Error.create(
            request,
            "forbidden",
            "Default priorities cannot be deleted.",
            "",
        )
    try:
        await asyncio.to_thread(BookingsService.delete_users_priority, priority_id)
        return EmptyResponse()
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete priority.",
            traceback.format_exc(),
        )


@admin_router.get(
    "/items/bookings/priority-rules",
    tags=[tag],
    response_model=list[PriorityRuleResponse],
    summary="List priority rules",
    description="Returns a list of all priority rules.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def list_priority_rules(request: Request):
    try:
        return await asyncio.to_thread(BookingsService.list_priority_rules)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve priority rules.",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/booking/availability/{item_type}/{item_id}",
    tags=[tag],
    response_model=AvailabilityResponse,
    summary="Get item availability",
    description="Returns item availability by crossing info with the resource planner.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_item_availability(
    request: Request,
    item_type: str = Path(..., description="Type of item (desktop or deployment)"),
    item_id: str = Path(..., description="ID of the item"),
) -> AvailabilityResponse:
    try:
        result = await asyncio.to_thread(
            BookingsService.get_item_availability,
            request.token_payload,
            item_type,
            item_id,
        )
        if isinstance(result, dict):
            return AvailabilityResponse(**result)
        return AvailabilityResponse()
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve item availability.",
            traceback.format_exc(),
        )


@admin_router.get(
    "/items/bookings/gpu",
    tags=[tag],
    response_model=list[GpuForecastProfile],
    summary="Get GPU bookings forecast",
    description="Returns GPU bookings forecast with current, 30min and 60min projections.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_gpu_bookings_forecast(request: Request):
    try:
        return await asyncio.to_thread(BookingsService.get_gpu_bookings_forecast)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve GPU bookings forecast.",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/item/booking/empty/{plan_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Empty all bookings in plan",
    description="Deletes all bookings associated with a plan.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def empty_booking_plan(request: Request, plan_id: str):
    try:
        await asyncio.to_thread(BookingsService.empty_planning, plan_id)
        return EmptyResponse()
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to empty bookings in plan.",
            traceback.format_exc(),
        )


@admin_router.get(
    "/item/booking/{booking_id}/plans",
    tags=[tag],
    response_model=list[BookingPlanResponse],
    summary="Get booking's plans",
    description="Returns the plans associated with a booking.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_booking_plans(request: Request, booking_id: str):
    try:
        return [
            BookingPlanResponse(**plan)
            for plan in await asyncio.to_thread(
                BookingsService.get_booking_plans, booking_id
            )
        ]
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve booking plans.",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/booking/reservables-available",
    tags=[tag],
    response_model=AvailableReservablesResponse,
    summary="Get available reservables",
    description="Returns available reservables for the current user.",
    operation_id="get_booking_reservables_available",
    responses={
        428: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_booking_reservables_available(request: Request):
    try:
        return AvailableReservablesResponse(
            reservables_available=await asyncio.to_thread(
                BookingsService.get_available_reservables, request.token_payload
            )
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve available reservables.",
            traceback.format_exc(),
        )
