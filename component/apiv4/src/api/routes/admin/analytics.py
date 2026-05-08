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
from typing import Literal

from api import admin_router, manager_router
from api.schemas.admin.analytics import (
    AnalyticsCategoriesRequest,
    AnalyticsGraphConfigResponse,
    AnalyticsGraphCreateRequest,
    AnalyticsGraphUpdateRequest,
    AnalyticsSuggestedRemovalsRequest,
    DesktopAnalyticsRequest,
    DesktopAnalyticsRow,
    EchartDailyItemsResponse,
    EchartRequest,
    EchartViewResponseRow,
    ResourceCountResponse,
    StorageUsageResponse,
    SuggestedRemovalsResponse,
)
from api.schemas.common import EmptyResponse, ErrorResponse
from api.services.admin.analytics import AdminAnalyticsService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse, Response

tag = "admin_analytics"


# =============================================================================
# STORAGE & RESOURCE ANALYTICS
# =============================================================================


@manager_router.post(
    "/analytics/storage",
    tags=[tag],
    response_model=StorageUsageResponse,
    summary="Get storage usage analytics",
    description="Returns storage usage analytics, optionally filtered by categories.",
    responses={500: {"model": ErrorResponse}},
)
async def analytics_storage(request: Request, data: AnalyticsCategoriesRequest):
    try:
        payload = request.token_payload
        categories = (
            [payload["category_id"]]
            if payload["role_id"] == "manager"
            else data.categories
        )
        result = await asyncio.to_thread(
            AdminAnalyticsService.storage_usage, categories
        )
        return JSONResponse(
            content=StorageUsageResponse(
                **(result if isinstance(result, dict) else {})
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get storage usage analytics",
            traceback.format_exc(),
        )


@manager_router.post(
    "/analytics/resources/count",
    tags=[tag],
    response_model=ResourceCountResponse,
    summary="Get resource count analytics",
    description="Returns resource count analytics (desktops, templates, media, etc.), optionally filtered by categories.",
    responses={500: {"model": ErrorResponse}},
)
async def analytics_resource_count(request: Request, data: AnalyticsCategoriesRequest):
    try:
        payload = request.token_payload
        categories = (
            [payload["category_id"]]
            if payload["role_id"] == "manager"
            else data.categories
        )
        result = await asyncio.to_thread(
            AdminAnalyticsService.resource_count, categories
        )
        return JSONResponse(
            content=ResourceCountResponse(
                **(result if isinstance(result, dict) else {})
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get resource count analytics",
            traceback.format_exc(),
        )


@manager_router.post(
    "/analytics/suggested_removals",
    tags=[tag],
    response_model=SuggestedRemovalsResponse,
    summary="Get suggested removals",
    description="Returns suggested resources for removal based on inactivity.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def analytics_suggested_removals(
    request: Request, data: AnalyticsSuggestedRemovalsRequest
):
    try:
        payload = request.token_payload
        categories = (
            [payload["category_id"]]
            if payload["role_id"] == "manager"
            else data.categories
        )
        result = await asyncio.to_thread(
            AdminAnalyticsService.suggested_removals,
            categories,
            months_without_use=data.months_without_use,
        )
        return JSONResponse(
            content=SuggestedRemovalsResponse(
                **(result if isinstance(result, dict) else {})
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get suggested removals",
            traceback.format_exc(),
        )


# =============================================================================
# GRAPH CONFIGURATION
# =============================================================================


@manager_router.get(
    "/analytics/graph",
    tags=[tag],
    response_model=list[AnalyticsGraphConfigResponse],
    summary="Get all analytics graph configurations",
    description="Returns all analytics graph configurations.",
    responses={500: {"model": ErrorResponse}},
)
async def analytics_graphs_conf_list(request: Request):
    try:
        result = await asyncio.to_thread(AdminAnalyticsService.get_usage_graphs_conf)
        return JSONResponse(
            content=[
                AnalyticsGraphConfigResponse(**row).model_dump(mode="json")
                for row in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get analytics graph configurations",
            traceback.format_exc(),
        )


@admin_router.get(
    "/analytics/graph/{conf_id}",
    tags=[tag],
    response_model=AnalyticsGraphConfigResponse,
    summary="Get analytics graph configuration",
    description="Returns a specific analytics graph configuration by ID.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def analytics_graph_conf_get(request: Request, conf_id: str):
    try:
        result = await asyncio.to_thread(
            AdminAnalyticsService.get_usage_graph_conf, conf_id
        )
        return JSONResponse(
            content=AnalyticsGraphConfigResponse(
                **(result if isinstance(result, dict) else {})
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get analytics graph configuration",
            traceback.format_exc(),
        )


@admin_router.post(
    "/analytics/graph",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Create analytics graph configuration",
    description="Creates a new analytics graph configuration.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def analytics_graph_conf_add(request: Request, data: AnalyticsGraphCreateRequest):
    try:
        await asyncio.to_thread(
            AdminAnalyticsService.add_usage_graph_conf,
            data.model_dump(exclude_none=True),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create analytics graph configuration",
            traceback.format_exc(),
        )


@admin_router.put(
    "/analytics/graph/{conf_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update analytics graph configuration",
    description="Updates an existing analytics graph configuration.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def analytics_graph_conf_update(
    request: Request, conf_id: str, data: AnalyticsGraphUpdateRequest
):
    try:
        await asyncio.to_thread(
            AdminAnalyticsService.update_usage_graph_conf,
            conf_id,
            data.model_dump(exclude_none=True),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update analytics graph configuration",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/analytics/graph/{conf_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete analytics graph configuration",
    description="Deletes an analytics graph configuration by ID.",
    responses={500: {"model": ErrorResponse}},
)
async def analytics_graph_conf_delete(request: Request, conf_id: str):
    try:
        await asyncio.to_thread(AdminAnalyticsService.delete_usage_graph_conf, conf_id)
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete analytics graph configuration",
            traceback.format_exc(),
        )


# =============================================================================
# DESKTOP ANALYTICS
# =============================================================================


@admin_router.post(
    "/analytics/desktops/less_used",
    tags=[tag],
    response_model=list[DesktopAnalyticsRow],
    summary="Get least used desktops",
    description="Returns desktops that have been least used within the specified period.",
    responses={500: {"model": ErrorResponse}},
)
async def analytics_desktops_less_used(request: Request, data: DesktopAnalyticsRequest):
    try:
        result = await asyncio.to_thread(
            AdminAnalyticsService.get_desktops_less_used,
            data.days_before,
            data.limit,
            data.not_in_directory_path,
            data.status or False,
        )
        return JSONResponse(
            content=[
                DesktopAnalyticsRow(**row).model_dump(mode="json")
                for row in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get least used desktops",
            traceback.format_exc(),
        )


@admin_router.post(
    "/analytics/desktops/recently_used",
    tags=[tag],
    response_model=list[DesktopAnalyticsRow],
    summary="Get recently used desktops",
    description="Returns desktops that have been recently used within the specified period.",
    responses={500: {"model": ErrorResponse}},
)
async def analytics_desktops_recently_used(
    request: Request, data: DesktopAnalyticsRequest
):
    try:
        result = await asyncio.to_thread(
            AdminAnalyticsService.get_desktops_recently_used,
            data.days_before,
            data.limit,
            data.not_in_directory_path,
            data.status or False,
        )
        return JSONResponse(
            content=[
                DesktopAnalyticsRow(**row).model_dump(mode="json")
                for row in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get recently used desktops",
            traceback.format_exc(),
        )


@admin_router.post(
    "/analytics/desktops/most_used",
    tags=[tag],
    response_model=list[DesktopAnalyticsRow],
    summary="Get most used desktops",
    description="Returns desktops that have been most frequently started within the specified period.",
    responses={500: {"model": ErrorResponse}},
)
async def analytics_desktops_most_used(request: Request, data: DesktopAnalyticsRequest):
    try:
        result = await asyncio.to_thread(
            AdminAnalyticsService.get_desktops_most_used,
            data.days_before,
            data.limit,
            data.not_in_directory_path,
            data.status or False,
        )
        return JSONResponse(
            content=[
                DesktopAnalyticsRow(**row).model_dump(mode="json")
                for row in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get most used desktops",
            traceback.format_exc(),
        )


# =============================================================================
# ECHART DATA
# =============================================================================


@admin_router.post(
    "/admin/echart/daily_items",
    tags=[tag],
    response_model=EchartDailyItemsResponse,
    summary="Get echart daily-items data",
    description="Returns ``{x, series}`` bucketed by ``(year, month, day)``"
    " of ``table[date_field]``. Distinct from the other echart views which"
    " return ``list[{value, name}]``.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_echart_daily_items(
    request: Request,
    data: EchartRequest,
):
    try:
        result = await asyncio.to_thread(
            AdminAnalyticsService.get_daily_items, data.table, data.date_field
        )
        return JSONResponse(
            content=EchartDailyItemsResponse(**(result or {})).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get echart daily-items data",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/echart/{view}",
    tags=[tag],
    response_model=list[EchartViewResponseRow],
    summary="Get echart data",
    description="Returns chart data for the specified view type."
    " For ``daily_items`` see ``/admin/echart/daily_items``.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_echart(
    request: Request,
    view: Literal[
        "grouped_items",
        "grouped_unique_items",
        "nested_array_grouped_items",
    ],
    data: EchartRequest,
):
    try:
        if view == "grouped_items":
            result = await asyncio.to_thread(
                AdminAnalyticsService.get_grouped_data, data.table, data.group_field
            )
        elif view == "grouped_unique_items":
            result = await asyncio.to_thread(
                AdminAnalyticsService.get_grouped_unique_data,
                data.table,
                data.group_field,
                data.unique_field,
            )
        else:  # view == "nested_array_grouped_items" — Literal route guard ensures
            result = await asyncio.to_thread(
                AdminAnalyticsService.get_nested_array_grouped_data,
                data.table,
                data.nested_array_field,
                data.group_field,
            )
        return JSONResponse(
            content=[
                EchartViewResponseRow(**row).model_dump(mode="json")
                for row in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get echart data",
            traceback.format_exc(),
        )
