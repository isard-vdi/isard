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

import traceback

from api import admin_router, manager_router
from api.schemas.admin_analytics import (
    AnalyticsCategoriesRequest,
    AnalyticsGraphCreateRequest,
    AnalyticsGraphUpdateRequest,
    AnalyticsSuggestedRemovalsRequest,
    DesktopAnalyticsRequest,
    EchartRequest,
)
from api.schemas.common import EmptyResponse, ErrorResponse
from api.services.admin_analytics import AdminAnalyticsService
from api.services.error import Error
from fastapi import Path, Request
from fastapi.responses import JSONResponse

tag = "admin_analytics"


# =============================================================================
# STORAGE & RESOURCE ANALYTICS
# =============================================================================


@manager_router.post(
    "/analytics/storage",
    tags=[tag],
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
        result = AdminAnalyticsService.storage_usage(categories)
        return JSONResponse(content=result, status_code=200)
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
        result = AdminAnalyticsService.resource_count(categories)
        return JSONResponse(content=result, status_code=200)
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
        result = AdminAnalyticsService.suggested_removals(
            categories, months_without_use=data.months_without_use
        )
        return JSONResponse(content=result, status_code=200)
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
    summary="Get all analytics graph configurations",
    description="Returns all analytics graph configurations.",
    responses={500: {"model": ErrorResponse}},
)
async def analytics_graphs_conf_list(request: Request):
    try:
        result = AdminAnalyticsService.get_usage_graphs_conf()
        return JSONResponse(content=result, status_code=200)
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
    summary="Get analytics graph configuration",
    description="Returns a specific analytics graph configuration by ID.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def analytics_graph_conf_get(request: Request, conf_id: str):
    try:
        result = AdminAnalyticsService.get_usage_graph_conf(conf_id)
        return JSONResponse(content=result, status_code=200)
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
    summary="Create analytics graph configuration",
    description="Creates a new analytics graph configuration.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def analytics_graph_conf_add(request: Request, data: AnalyticsGraphCreateRequest):
    try:
        AdminAnalyticsService.add_usage_graph_conf(data.model_dump(exclude_none=True))
        return JSONResponse(content={}, status_code=200)
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
        AdminAnalyticsService.update_usage_graph_conf(
            conf_id, data.model_dump(exclude_none=True)
        )
        return JSONResponse(content={}, status_code=200)
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
    summary="Delete analytics graph configuration",
    description="Deletes an analytics graph configuration by ID.",
    responses={500: {"model": ErrorResponse}},
)
async def analytics_graph_conf_delete(request: Request, conf_id: str):
    try:
        AdminAnalyticsService.delete_usage_graph_conf(conf_id)
        return JSONResponse(content={}, status_code=200)
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
    summary="Get least used desktops",
    description="Returns desktops that have been least used within the specified period.",
    responses={500: {"model": ErrorResponse}},
)
async def analytics_desktops_less_used(request: Request, data: DesktopAnalyticsRequest):
    try:
        result = AdminAnalyticsService.get_desktops_less_used(
            data.days_before,
            data.limit,
            data.not_in_directory_path,
            data.status or False,
        )
        return JSONResponse(content=result, status_code=200)
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
    summary="Get recently used desktops",
    description="Returns desktops that have been recently used within the specified period.",
    responses={500: {"model": ErrorResponse}},
)
async def analytics_desktops_recently_used(
    request: Request, data: DesktopAnalyticsRequest
):
    try:
        result = AdminAnalyticsService.get_desktops_recently_used(
            data.days_before,
            data.limit,
            data.not_in_directory_path,
            data.status or False,
        )
        return JSONResponse(content=result, status_code=200)
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
    summary="Get most used desktops",
    description="Returns desktops that have been most frequently started within the specified period.",
    responses={500: {"model": ErrorResponse}},
)
async def analytics_desktops_most_used(request: Request, data: DesktopAnalyticsRequest):
    try:
        result = AdminAnalyticsService.get_desktops_most_used(
            data.days_before,
            data.limit,
            data.not_in_directory_path,
            data.status or False,
        )
        return JSONResponse(content=result, status_code=200)
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
    "/admin/echart/{view}",
    tags=[tag],
    summary="Get echart data",
    description="Returns chart data for the specified view type (daily_items, grouped_items, grouped_unique_items, nested_array_grouped_items).",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_echart(request: Request, view: str, data: EchartRequest):
    try:
        if view == "daily_items":
            result = AdminAnalyticsService.get_daily_items(data.table, data.date_field)
        elif view == "grouped_items":
            result = AdminAnalyticsService.get_grouped_data(
                data.table, data.group_field
            )
        elif view == "grouped_unique_items":
            result = AdminAnalyticsService.get_grouped_unique_data(
                data.table, data.group_field, data.unique_field
            )
        elif view == "nested_array_grouped_items":
            result = AdminAnalyticsService.get_nested_array_grouped_data(
                data.table, data.nested_array_field, data.group_field
            )
        else:
            raise Error("bad_request", f"Unknown echart view: {view}")
        return JSONResponse(content=result, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get echart data",
            traceback.format_exc(),
        )
