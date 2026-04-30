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
from datetime import datetime

import pytz
from api import admin_router, manager_router
from api.schemas.admin.usage import (
    UsageConsumptionRequest,
    UsageCreditCreateRequest,
    UsageCreditUpdateRequest,
    UsageGroupingCreateRequest,
    UsageGroupingUpdateRequest,
    UsageLimitCreateRequest,
    UsageLimitUpdateRequest,
    UsageParameterCreateRequest,
    UsageParameterIdsRequest,
    UsageParameterUpdateRequest,
    UsageResetDatesRequest,
    UsageStartEndRequest,
)
from api.schemas.common import EmptyResponse, ErrorResponse
from api.services.admin.usage import AdminUsageService
from api.services.error import Error
from fastapi import Path, Request

tag = "admin_usage"


# =============================================================================
# CONSUMPTION
# =============================================================================


@manager_router.put(
    "/admin/usage",
    tags=[tag],
    response_model=list[dict],
    summary="Get usage consumption between dates",
    description="Returns usage consumption data between the specified dates with optional filtering.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_consumption(
    request: Request, data: UsageConsumptionRequest
) -> list[dict]:
    try:
        payload = request.token_payload
        filters = data.model_dump(exclude_none=True)
        AdminUsageService.check_item_ownership(payload, filters)
        result = AdminUsageService.get_usage_consumption_between_dates(
            filters.get("start_date"),
            filters.get("end_date"),
            filters.get("items_ids"),
            filters.get("item_type"),
            filters.get("grouping"),
        )
        return result or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get usage consumption",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/usage/start_end",
    tags=[tag],
    response_model=dict,
    summary="Get start/end consumption",
    description="Returns consumption data at start and end dates for comparison.",
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_start_end(request: Request, data: UsageStartEndRequest) -> dict:
    try:
        payload = request.token_payload
        filters = data.model_dump(exclude_none=True)
        if (
            payload["role_id"] != "admin"
            and filters.get("item_consumer") == "hypervisor"
        ):
            raise Error("forbidden", "Not enough rights to access hypervisor usage")
        AdminUsageService.check_item_ownership(payload, filters)
        result = AdminUsageService.get_start_end_consumption(
            filters.get("start_date"),
            filters.get("end_date"),
            filters.get("items_ids"),
            filters.get("item_type"),
            filters.get("item_consumer"),
            filters.get("grouping"),
            payload["category_id"] if payload["role_id"] == "manager" else None,
        )
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get start/end consumption",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/usage/consumers/{item_type}",
    tags=[tag],
    response_model=list[str],
    summary="Get usage consumers for item type",
    description="Returns distinct consumer types for the given item type.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_usage_consumers(request: Request, item_type: str) -> list[str]:
    try:
        payload = request.token_payload
        consumers = AdminUsageService.get_usage_consumers(item_type) or []
        if payload["role_id"] != "admin" and "hypervisor" in consumers:
            consumers.remove("hypervisor")
        return consumers
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get usage consumers",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/usage/consumers",
    tags=[tag],
    response_model=dict,
    summary="Count usage consumers",
    description="Returns the total count of usage consumption records.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_usage_consumers_count(request: Request) -> dict:
    try:
        result = AdminUsageService.count_usage_consumers()
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to count usage consumers",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/usage/distinct_items/{item_consumer}/{start}/{end}",
    tags=[tag],
    response_model=list[dict],
    summary="Get distinct usage items",
    description="Returns distinct items for a consumer type within a date range.",
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_distinct_items(
    request: Request,
    item_consumer: str,
    start: str,
    end: str,
) -> list[dict]:
    try:
        payload = request.token_payload
        if payload["role_id"] != "admin" and item_consumer == "hypervisor":
            raise Error("forbidden", "Not enough rights to access hypervisor usage")
        result = AdminUsageService.get_usage_distinct_items(
            item_consumer,
            start,
            end,
            payload["category_id"] if payload["role_id"] == "manager" else None,
        )
        return result or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get distinct usage items",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/usage/consolidate",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Consolidate all consumption data",
    description="Triggers consolidation of all usage consumption data.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_usage_consolidate(request: Request) -> EmptyResponse:
    try:
        AdminUsageService.consolidate_consumptions()
        return EmptyResponse()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to consolidate consumption",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/usage/consolidate/{item_type}/{days}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Consolidate consumption for item type with days",
    description="Triggers consolidation of usage consumption data for a specific item type and number of days.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_usage_consolidate_item_days(
    request: Request,
    item_type: str,
    days: int = 29,
) -> EmptyResponse:
    try:
        AdminUsageService.consolidate_consumptions(item_type, days)
        return EmptyResponse()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to consolidate consumption",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/usage/consolidate/{item_type}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Consolidate consumption for item type",
    description="Triggers consolidation of usage consumption data for a specific item type.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_usage_consolidate_item(
    request: Request,
    item_type: str,
) -> EmptyResponse:
    try:
        AdminUsageService.consolidate_consumptions(item_type, 29)
        return EmptyResponse()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to consolidate consumption",
            traceback.format_exc(),
        )


# =============================================================================
# PARAMETERS
# =============================================================================


@admin_router.get(
    "/admin/usage/parameters",
    tags=[tag],
    response_model=list[dict],
    summary="Get all usage parameters",
    description="Returns all usage parameters.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_usage_parameters_list(request: Request) -> list[dict]:
    try:
        result = AdminUsageService.get_usage_parameters()
        return result or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get usage parameters",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/usage/list_parameters",
    tags=[tag],
    response_model=list[dict] | dict,
    summary="Get usage parameters by IDs",
    description="Returns usage parameters filtered by a list of IDs.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_usage_list_parameters(
    request: Request, data: UsageParameterIdsRequest
) -> list[dict] | dict:
    try:
        if data.ids:
            return AdminUsageService.get_usage_parameters(data.ids) or []
        return {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list usage parameters",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/usage/parameters",
    tags=[tag],
    response_model=dict,
    summary="Create usage parameter",
    description="Creates a new usage parameter.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_parameters_add(
    request: Request, data: UsageParameterCreateRequest
) -> dict:
    try:
        result = AdminUsageService.add_usage_parameters(data.model_dump())
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create usage parameter",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/usage/parameters/{parameter_id}",
    tags=[tag],
    response_model=dict,
    summary="Update usage parameter",
    description="Updates an existing usage parameter.",
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_parameters_update(
    request: Request,
    parameter_id: str,
    data: UsageParameterUpdateRequest,
) -> dict:
    try:
        result = AdminUsageService.update_usage_parameters(data.model_dump())
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update usage parameter",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/usage/parameters/{parameter_id}",
    tags=[tag],
    response_model=dict,
    summary="Delete usage parameter",
    description="Deletes a usage parameter by ID.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_parameters_delete(
    request: Request,
    parameter_id: str = Path(..., description="Parameter ID"),
) -> dict:
    try:
        result = AdminUsageService.delete_usage_parameters(parameter_id)
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete usage parameter",
            traceback.format_exc(),
        )


# =============================================================================
# LIMITS
# =============================================================================


@admin_router.get(
    "/admin/usage/limits",
    tags=[tag],
    response_model=list[dict],
    summary="Get all usage limits",
    description="Returns all usage limits.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_usage_limits_list(request: Request) -> list[dict]:
    try:
        result = AdminUsageService.get_usage_limits()
        return result or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get usage limits",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/usage/limits",
    tags=[tag],
    response_model=dict,
    summary="Create usage limit",
    description="Creates a new usage limit.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_limits_add(
    request: Request, data: UsageLimitCreateRequest
) -> dict:
    try:
        result = AdminUsageService.add_usage_limits(
            data.name, data.desc, data.limits.model_dump()
        )
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create usage limit",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/usage/limits/{limit_id}",
    tags=[tag],
    response_model=dict,
    summary="Update usage limit",
    description="Updates an existing usage limit.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_limits_update(
    request: Request,
    limit_id: str,
    data: UsageLimitUpdateRequest,
) -> dict:
    try:
        result = AdminUsageService.update_usage_limits(
            limit_id, data.name, data.desc, data.limits.model_dump()
        )
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update usage limit",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/usage/limits/{limit_id}",
    tags=[tag],
    response_model=dict,
    summary="Delete usage limit",
    description="Deletes a usage limit by ID.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_limits_delete(
    request: Request,
    limit_id: str = Path(..., description="Limit ID"),
) -> dict:
    try:
        result = AdminUsageService.delete_usage_limits(limit_id)
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete usage limit",
            traceback.format_exc(),
        )


# =============================================================================
# GROUPINGS
# =============================================================================


@admin_router.get(
    "/admin/usage/groupings",
    tags=[tag],
    response_model=list[dict],
    summary="Get all usage groupings",
    description="Returns all usage groupings (system + custom).",
    responses={500: {"model": ErrorResponse}},
)
async def admin_usage_groupings_list(request: Request) -> list[dict]:
    try:
        result = AdminUsageService.get_usage_groupings()
        return result or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get usage groupings",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/usage/groupings_dropdown",
    tags=[tag],
    response_model=list[dict],
    summary="Get usage groupings dropdown",
    description="Returns usage groupings structured for dropdown menus.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_usage_groupings_dropdown(request: Request) -> list[dict]:
    try:
        result = AdminUsageService.get_usage_groupings_dropdown()
        return result or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get usage groupings dropdown",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/usage/grouping/{grouping_id}",
    tags=[tag],
    response_model=dict,
    summary="Get usage grouping by ID",
    description="Returns a specific usage grouping.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_grouping_get(request: Request, grouping_id: str) -> dict:
    try:
        result = AdminUsageService.get_usage_grouping(grouping_id)
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get usage grouping",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/usage/groupings",
    tags=[tag],
    response_model=dict,
    summary="Create usage grouping",
    description="Creates a new usage grouping.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_groupings_add(
    request: Request, data: UsageGroupingCreateRequest
) -> dict:
    try:
        result = AdminUsageService.add_usage_grouping(data.model_dump())
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create usage grouping",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/usage/groupings/{grouping_id}",
    tags=[tag],
    response_model=dict,
    summary="Update usage grouping",
    description="Updates an existing usage grouping.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_groupings_update(
    request: Request,
    grouping_id: str,
    data: UsageGroupingUpdateRequest,
) -> dict:
    try:
        result = AdminUsageService.update_usage_grouping(data.model_dump())
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update usage grouping",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/usage/groupings/{grouping_id}",
    tags=[tag],
    response_model=dict,
    summary="Delete usage grouping",
    description="Deletes a usage grouping by ID.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_groupings_delete(
    request: Request,
    grouping_id: str = Path(..., description="Grouping ID"),
) -> dict:
    try:
        result = AdminUsageService.delete_usage_grouping(grouping_id)
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete usage grouping",
            traceback.format_exc(),
        )


# =============================================================================
# CREDITS
# =============================================================================


@admin_router.get(
    "/admin/usage/category_credits",
    tags=[tag],
    response_model=list[dict],
    summary="Get all usage credits",
    description="Returns all usage credits with category names and grouping names.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_usage_all_credits(request: Request) -> list[dict]:
    try:
        result = AdminUsageService.get_all_usage_credits()
        return result or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get all usage credits",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/usage/category_credits/{category_credit_id}",
    tags=[tag],
    response_model=dict,
    summary="Get usage credit by ID",
    description="Returns a specific usage credit.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_credits_by_id(request: Request, category_credit_id: str) -> dict:
    try:
        result = AdminUsageService.get_usage_credits_by_id(category_credit_id)
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get usage credit",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/usage/credits/{consumer}/{item_type}/{item_id}/{grouping_id}/{start_date}/{end_date}",
    tags=[tag],
    response_model=list[dict],
    summary="Get usage credits for item",
    description="Returns usage credits for a specific item, type, grouping, and date range.",
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_credits(
    request: Request,
    consumer: str,
    item_type: str,
    item_id: str,
    grouping_id: str,
    start_date: str,
    end_date: str,
) -> list[dict]:
    try:
        payload = request.token_payload
        if (
            consumer == "category"
            and payload["role_id"] == "manager"
            and payload["category_id"] != item_id
        ):
            raise Error("forbidden", "You are not allowed to access this category")
        result = AdminUsageService.get_usage_credits(
            item_id, item_type, grouping_id, start_date, end_date
        )
        return result or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get usage credits",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/usage/credits",
    tags=[tag],
    response_model=dict,
    summary="Create usage credit",
    description="Creates usage credits for one or more items.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_credits_add(
    request: Request, data: UsageCreditCreateRequest
) -> dict:
    try:
        result = AdminUsageService.add_usage_credit(data.model_dump())
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create usage credit",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/usage/credits/{credit_id}",
    tags=[tag],
    response_model=dict,
    summary="Update usage credit",
    description="Updates an existing usage credit.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_credits_update(
    request: Request,
    credit_id: str,
    data: UsageCreditUpdateRequest,
) -> dict:
    try:
        result = AdminUsageService.update_usage_credit(
            credit_id, data.model_dump(exclude_none=True)
        )
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update usage credit",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/usage/credits/{credit_id}",
    tags=[tag],
    response_model=dict,
    summary="Delete usage credit",
    description="Deletes a usage credit by ID.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_credits_delete(
    request: Request,
    credit_id: str = Path(..., description="Credit ID"),
) -> dict:
    try:
        result = AdminUsageService.delete_usage_credit(credit_id)
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete usage credit",
            traceback.format_exc(),
        )


# =============================================================================
# MISC
# =============================================================================


@admin_router.put(
    "/admin/usage/unify/{item_id}/item_name",
    tags=[tag],
    response_model=dict,
    summary="Unify item name in consumption records",
    description="Unifies the item name across all consumption records for the given item.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_usage_unify_item_name(request: Request, item_id: str) -> dict:
    try:
        name = AdminUsageService.unify_item_name(item_id)
        return {"name": name}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to unify item name",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/usage/reset_date",
    tags=[tag],
    response_model=list[str],
    summary="Get all reset dates",
    description="Returns all usage reset dates.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_usage_reset_dates_all(request: Request) -> list[str]:
    try:
        reset_dates = AdminUsageService.get_reset_dates()
        return [date.strftime("%m/%d/%Y") for date in reset_dates]
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get reset dates",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/usage/reset_date/{start_date}/{end_date}",
    tags=[tag],
    response_model=list[str],
    summary="Get reset dates in range",
    description="Returns usage reset dates within the specified date range.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_usage_reset_dates_range(
    request: Request, start_date: str, end_date: str
) -> list[str]:
    try:
        try:
            start = datetime.strptime(start_date, "%Y-%m-%d").replace(
                tzinfo=pytz.timezone("UTC")
            )
            end = datetime.strptime(end_date, "%Y-%m-%d").replace(
                tzinfo=pytz.timezone("UTC")
            )
        except ValueError:
            raise Error(
                "bad_request",
                "Invalid date: expected YYYY-MM-DD",
                description_code="invalid_date",
            )
        reset_dates = AdminUsageService.get_reset_dates(start, end)
        return [date.strftime("%m/%d/%Y") for date in reset_dates]
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get reset dates",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/usage/reset_dates",
    tags=[tag],
    response_model=list[str],
    summary="Set usage reset dates",
    description="Replaces all usage reset dates with the provided list.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_reset_dates_add(
    request: Request, data: UsageResetDatesRequest
) -> list[str]:
    try:
        parsed_dates = []
        try:
            parsed_dates = [datetime.strptime(d, "%m/%d/%Y") for d in data.date_list]
        except Error:
            raise
        except Exception:
            parsed_dates = []
        AdminUsageService.add_reset_dates(parsed_dates)
        return data.date_list
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to set reset dates",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/usage/delete_data",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete all consumption data",
    description="Deletes all usage consumption data. This operation runs in the background.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_usage_delete_consumption_data(request: Request) -> EmptyResponse:
    try:
        # Run in background like v3's gevent.spawn
        asyncio.get_event_loop().run_in_executor(
            None, AdminUsageService.delete_all_consumption_data
        )
        return EmptyResponse()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete consumption data",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/usage/check/overlapping/{credit_id}/{start_date}/{end_date}",
    tags=[tag],
    response_model=dict,
    summary="Check overlapping credits",
    description="Checks if there are overlapping credit intervals for the given credit and date range.",
    responses={
        400: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_usage_check_overlapping(
    request: Request,
    credit_id: str,
    start_date: str,
    end_date: str,
) -> dict:
    try:
        credit = AdminUsageService.get_usage_credits_by_id(credit_id)
        start = start_date if start_date != "null" else None
        end = end_date if end_date != "null" else None
        try:
            start = datetime.strptime(start, "%Y-%m-%d").astimezone(pytz.UTC)
            if end:
                end = datetime.strptime(end, "%Y-%m-%d").astimezone(pytz.UTC)
        except Error:
            raise
        except Exception:
            raise Error(
                "bad_request", "Incorrect date format. Expected format: %Y-%m-%d"
            )
        result = AdminUsageService.check_overlapping_credits(
            credit["item_id"],
            credit["item_type"],
            credit["grouping_id"],
            start,
            end,
            credit_id,
        )
        return result if isinstance(result, dict) else {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to check overlapping credits",
            traceback.format_exc(),
        )
