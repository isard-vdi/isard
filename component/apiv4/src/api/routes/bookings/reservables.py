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
import logging
import traceback
from datetime import datetime
from typing import Literal, Optional

log = logging.getLogger("apiv4")

from api import admin_router, token_router
from api.schemas.common import EmptyResponse, ErrorResponse, SimpleResponse
from api.schemas.reservables import (
    AddReservableItemRequest,
    AvailableReservablesResponse,
    BookingProvisioningRequest,
    CheckLastResponse,
    CreatePlanRequest,
    EnableReservableRequest,
    ReservableDetailResponse,
    ReservableProfileResponse,
    ReservablesListResponse,
    ReservableSubitemResponse,
    UpdateReservableItemRequest,
)
from api.services.error import Error
from api.services.reservables import ReservableService
from fastapi import Path, Query, Request
from fastapi.responses import JSONResponse

tag = "reservables"


@admin_router.get(
    "/items/reservables",
    response_model=ReservablesListResponse,
    tags=[tag],
    summary="Get list of reservable types",
    description="Returns a list of all available reservable types (e.g., gpus, usbs).",
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_reservables(request: Request):
    """Get list of all reservable types."""
    try:
        reservables = await asyncio.to_thread(ReservableService.get_reservables)
        return ReservablesListResponse(reservables=reservables)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve reservables",
            traceback.format_exc(),
        )


# NOTE: this specific path MUST be registered BEFORE the generic
# ``/items/reservables/{reservable_type}`` below, otherwise FastAPI's
# path matcher resolves ``profiles`` as the ``reservable_type`` path
# parameter and the profiles handler becomes unreachable.
@admin_router.get(
    "/items/reservables/profiles/{reservable_type}",
    tags=[tag],
    response_model=list[ReservableProfileResponse],
    summary="List profiles for a reservable type",
    description=("Returns all profiles for a specific reservable type."),
    responses={
        500: {"model": ErrorResponse},
    },
)
async def list_profiles(
    request: Request,
    reservable_type: str = Path(..., description="The reservable type (e.g., 'gpus')"),
) -> list[ReservableProfileResponse]:
    try:
        items = (
            await asyncio.to_thread(ReservableService.list_profiles, reservable_type)
            or []
        )
        return [ReservableProfileResponse(**item) for item in items]
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve profiles for {reservable_type}",
            traceback.format_exc(),
        )


@admin_router.get(
    "/items/reservables/{reservable_type}",
    response_model=ReservableDetailResponse,
    tags=[tag],
    summary="Get items of a specific reservable type",
    description="Returns all items for a specific reservable type (e.g., all GPUs).",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_reservable_items(
    request: Request,
    reservable_type: str = Path(
        ..., description="The reservable type (e.g., 'gpus', 'usbs')"
    ),
):
    """
    Get all items for a specific reservable type
    """
    try:
        items = await asyncio.to_thread(
            ReservableService.get_reservable_detail, reservable_type
        )
        return ReservableDetailResponse(items=items)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve reservable items for {reservable_type}",
            traceback.format_exc(),
        )


@admin_router.get(
    "/items/reservables/{reservable_type}/{item_id}",
    tags=[tag],
    response_model=list[dict],
    summary="List subitems of a reservable item",
    description=(
        "Returns the catalog of subitems (e.g., vGPU profiles) for a "
        "specific reservable item. v3 parity for the admin Hypervisors "
    ),
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def list_reservable_subitems(
    request: Request,
    reservable_type: str = Path(
        ..., description="The reservable type (e.g., 'gpus', 'usbs')"
    ),
    item_id: str = Path(..., description="The reservable item ID"),
) -> list[dict]:
    try:
        return (
            await asyncio.to_thread(
                ReservableService.list_subitems, reservable_type, item_id
            )
            or []
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to list subitems of {reservable_type}/{item_id}",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/reservables/get-available",
    tags=[tag],
    response_model=AvailableReservablesResponse,
    summary="Get booking reservables available",
    description="Returns available reservables for booking.",
    operation_id="get_reservables_available",
)
async def get_booking_reservables_available(request: Request):
    try:
        return AvailableReservablesResponse(
            reservables_available=await asyncio.to_thread(
                ReservableService.get_available_reservables, request.token_payload
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


@admin_router.post(
    "/item/reservable/{reservable_type}",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Add new reservable item",
    description="Creates a new reservable item of the specified type.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def add_reservable_item(
    request: Request,
    reservable_type: str = Path(..., description="The reservable type (e.g., 'gpus')"),
    data: AddReservableItemRequest = ...,
) -> SimpleResponse:
    try:
        created = await asyncio.to_thread(
            ReservableService.add_item, reservable_type, data.model_dump()
        )
        return SimpleResponse(id=(created or {}).get("id", ""))
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to add reservable item for {reservable_type}",
            traceback.format_exc(),
        )


@admin_router.put(
    "/item/reservable/enable/{reservable_type}/{item_id}/{subitem_id}",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Enable or disable a reservable subitem",
    description=(
        "Enables or disables a specific reservable subitem (e.g., GPU "
        "profile). Pass ``?notify_user=true`` to fan out a ``deleted-gpu``"
        " email to every user whose desktops/deployments/bookings "
        "reference the reservable (v3 parity)."
    ),
    responses={
        500: {"model": ErrorResponse},
    },
)
async def enable_reservable_subitem(
    request: Request,
    reservable_type: str = Path(..., description="The reservable type"),
    item_id: str = Path(..., description="The item ID"),
    subitem_id: str = Path(..., description="The subitem ID"),
    data: EnableReservableRequest = ...,
    notify_user: bool = Query(
        False,
        description=(
            "If true, notify every affected user by email before the "
            "subitem is disabled. Ignored when ``enabled`` is true."
        ),
    ),
) -> SimpleResponse:
    try:
        await asyncio.to_thread(
            ReservableService.enable_subitem,
            reservable_type,
            item_id,
            subitem_id,
            data.enabled,
            notify_user=notify_user,
        )
        return SimpleResponse(id=item_id)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to enable/disable reservable subitem",
            traceback.format_exc(),
        )


@admin_router.get(
    "/item/reservable/enabled/{reservable_type}/{item_id}",
    tags=[tag],
    response_model=list[dict],
    summary="List enabled subitems",
    description="Returns the list of enabled subitems for a specific reservable item.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def list_enabled_subitems(
    request: Request,
    reservable_type: Literal["gpus", "usbs"] = Path(
        ..., description="The reservable type"
    ),
    item_id: str = Path(..., description="The item ID"),
) -> list[dict]:
    try:
        return (
            await asyncio.to_thread(
                ReservableService.list_subitems_enabled, reservable_type, item_id
            )
            or []
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve enabled subitems",
            traceback.format_exc(),
        )


@admin_router.get(
    "/item/reservable/check-last/{reservable_type}/{subitem_id}/{item_id}",
    tags=[tag],
    response_model=CheckLastResponse,
    summary="Check last subitem",
    description="Checks if a GPU profile was the last enabled and returns affected desktops and plans.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def check_last_subitem(
    request: Request,
    reservable_type: str = Path(..., description="The reservable type"),
    subitem_id: str = Path(..., description="The subitem ID"),
    item_id: str = Path(..., description="The item ID"),
):
    try:
        data = await asyncio.to_thread(
            ReservableService.check_last_subitem, reservable_type, subitem_id, item_id
        )
        return CheckLastResponse(**data)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to check last subitem.",
            traceback.format_exc(),
        )


@admin_router.get(
    "/item/reservable/check-last/{reservable_type}/{item_id}",
    tags=[tag],
    response_model=CheckLastResponse,
    summary="Check last item",
    description="Checks if a GPU item was the last enabled and returns affected desktops and plans.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def check_last_item(
    request: Request,
    reservable_type: str = Path(..., description="The reservable type"),
    item_id: str = Path(..., description="The item ID"),
):
    try:
        data = await asyncio.to_thread(
            ReservableService.check_last_item, reservable_type, item_id
        )
        return CheckLastResponse(**data)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to check last item.",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/item/reservable/{reservable_type}/{item_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete reservable item",
    description=(
        "Deletes a reservable item and all its associated plans and "
        "bookings. Pass ``?notify_user=true`` to fan out a "
        "``deleted-gpu`` email to affected users first (v3 parity)."
    ),
    responses={
        500: {"model": ErrorResponse},
    },
)
async def delete_reservable_item(
    request: Request,
    reservable_type: str = Path(..., description="The reservable type"),
    item_id: str = Path(..., description="The item ID"),
    notify_user: bool = Query(
        False,
        description=(
            "If true, fan out a ``deleted-gpu`` email to every user "
            "affected by the deletion before removing the item."
        ),
    ),
):
    try:
        await asyncio.to_thread(
            ReservableService.delete_item,
            reservable_type,
            item_id,
            notify_user=notify_user,
        )
        return EmptyResponse()
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete reservable item.",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/reservables/{reservable_type}/{item_id}",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Update reservable item",
    description="Update name and description of a reservable item (e.g., GPU).",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_reservable_item(
    request: Request,
    reservable_type: str = Path(..., description="The reservable type (e.g., gpus)"),
    item_id: str = Path(..., description="The item ID"),
    data: UpdateReservableItemRequest = ...,
) -> SimpleResponse:
    try:
        await asyncio.to_thread(
            ReservableService.update_item,
            reservable_type,
            item_id,
            data.model_dump(exclude_none=True),
        )
        return SimpleResponse(id=item_id)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update reservable item.",
            traceback.format_exc(),
        )


@admin_router.get(
    "/items/reservables-planner",
    tags=[tag],
    response_model=list[dict],
    summary="List all plans",
    description="Returns all resource planner plans.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def list_all_plans(request: Request) -> list[dict]:
    try:
        plans = await asyncio.to_thread(ReservableService.list_all_plans)
        return plans or []
    except Error:
        raise
    except Exception as e:
        log.error("reservables-planner error: %s", traceback.format_exc())
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve plans.",
            traceback.format_exc(),
        )


@admin_router.get(
    "/item/reservables-planner/check-integrity",
    tags=[tag],
    response_model=dict,
    summary="Check planning integrity",
    description="Checks if any plan item IDs are overlapped.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def check_integrity(request: Request) -> dict:
    try:
        result = await asyncio.to_thread(ReservableService.check_integrity)
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to check planning integrity.",
            traceback.format_exc(),
        )


@admin_router.get(
    "/item/reservables-planner/actual-plan/{item_id}",
    tags=[tag],
    response_model=dict,
    summary="Get actual plan for item",
    description="Returns the current active plan for a specific item.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_actual_plan(
    request: Request,
    item_id: str = Path(..., description="The item ID"),
) -> dict:
    try:
        result = await asyncio.to_thread(ReservableService.get_actual_plan, item_id)
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve actual plan.",
            traceback.format_exc(),
        )


@admin_router.get(
    "/item/reservables-planner/{plan_id}/bookings",
    tags=[tag],
    response_model=list[dict],
    summary="Get plan bookings",
    description="Returns all bookings associated with a specific plan.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_plan_bookings(
    request: Request,
    plan_id: str = Path(..., description="The plan ID"),
) -> list[dict]:
    try:
        return (
            await asyncio.to_thread(ReservableService.get_plan_bookings, plan_id) or []
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve plan bookings.",
            traceback.format_exc(),
        )


@admin_router.get(
    "/item/reservables-planner/by-item/{item_id}",
    tags=[tag],
    response_model=list[dict],
    summary="Get plans for item",
    description="Returns all plans for a specific item.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_item_plans(
    request: Request,
    item_id: str = Path(..., description="The item ID"),
) -> list[dict]:
    try:
        return await asyncio.to_thread(ReservableService.get_item_plans, item_id) or []
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve item plans.",
            traceback.format_exc(),
        )


@admin_router.post(
    "/item/reservables-planner",
    tags=[tag],
    response_model=dict,
    summary="Create plan",
    description="Creates a new resource planner plan.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def create_plan(request: Request, data: CreatePlanRequest) -> dict:
    try:
        plan_data = {
            "item_type": data.item_type,
            "item_id": data.item_id,
            "subitem_id": data.subitem_id,
            "start": data.start,
            "end": data.end,
        }
        result = await asyncio.to_thread(
            ReservableService.add_plan, request.token_payload, plan_data
        )
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create plan.",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/item/reservables-planner/{plan_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete plan",
    description="Deletes a resource planner plan and its associated bookings.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def delete_plan(
    request: Request,
    plan_id: str = Path(..., description="The plan ID"),
):
    try:
        await asyncio.to_thread(ReservableService.delete_plan, plan_id)
        return EmptyResponse()
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete plan.",
            traceback.format_exc(),
        )


@admin_router.put(
    "/item/reservables-planner/{plan_id}/{start}/{end}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update plan",
    description="Updates a resource planner plan's start and end dates.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def update_plan(
    request: Request,
    plan_id: str = Path(..., description="The plan ID"),
    start: datetime = Path(..., description="New start datetime (ISO 8601)"),
    end: datetime = Path(..., description="New end datetime (ISO 8601)"),
):
    # ``datetime`` path params let FastAPI auto-validate ISO 8601 at
    # the route boundary so a malformed string returns 422 with a
    # proper datetime_parsing error instead of falling through to the
    # service's bare parse → 500. The service still receives strings
    # for backwards compatibility (it formats them itself), so coerce
    # back to ISO 8601 before forwarding.
    try:
        await asyncio.to_thread(
            ReservableService.update_plan,
            request.token_payload,
            plan_id,
            start.isoformat(),
            end.isoformat(),
        )
        return EmptyResponse()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update plan.",
            traceback.format_exc(),
        )


@token_router.post(
    "/item/reservables-planner/booking-provisioning",
    tags=[tag],
    response_model=dict,
    summary="Booking provisioning",
    description="Determines where a new booking can be placed based on available resources.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def booking_provisioning(
    request: Request, data: BookingProvisioningRequest
) -> dict:
    try:
        result = await asyncio.to_thread(
            ReservableService.booking_provisioning,
            request.token_payload,
            data.subitems,
            data.units,
            data.priority,
            data.block_interval,
        )
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to compute booking provisioning.",
            traceback.format_exc(),
        )
