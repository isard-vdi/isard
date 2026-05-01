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

# NOTE on route ordering:
# FastAPI matches routes in declaration order, so all LITERAL sub-paths
# under a given prefix must be declared BEFORE any sibling catch-all
# /{param} route in the same file, otherwise the catch-all shadows them.
# In this file:
#   - /stats/categories, /stats/categories/limits, /stats/categories/deployments
#     must come BEFORE /stats/categories/{kind} and /stats/{kind}
#   - /stats/domains/status and /stats/category/status must come BEFORE
#     /stats/{kind} (they don't actually collide because they have two
#     segments after /stats/, but we keep the defensive order for clarity)

import asyncio
import traceback
from typing import Literal

from api import admin_router
from api.schemas.admin.stats import (
    StatsCategoriesDeploymentsResponse,
    StatsCategoriesResponse,
    StatsDomainsStatusResponse,
    StatsGenericResponse,
    StatsKindDesktop,
    StatsKindHypervisor,
    StatsKindTemplate,
    StatsKindUser,
)
from api.schemas.common import ErrorResponse
from api.services.admin.stats import AdminStatsService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse

tag = "admin_stats"


# =============================================================================
# GENERAL STATS
# =============================================================================


@admin_router.get(
    "/stats",
    tags=[tag],
    summary="Get general statistics",
    description="Returns general statistics including users, desktops, and templates.",
    response_model=StatsGenericResponse,
    responses={500: {"model": ErrorResponse}},
)
async def stats_general(request: Request) -> StatsGenericResponse:
    try:
        result = await asyncio.to_thread(AdminStatsService.get_general_stats)
        return StatsGenericResponse(**(result or {}))
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get general statistics",
            traceback.format_exc(),
        )


@admin_router.get(
    "/stats/desktops/status",
    tags=[tag],
    summary="Get desktop status statistics",
    description="Returns desktop statistics grouped by status.",
    response_model=StatsGenericResponse,
    responses={500: {"model": ErrorResponse}},
)
async def stats_desktops_status(request: Request) -> StatsGenericResponse:
    try:
        # Service returns a single ``{"total": int, "status": {<status>: int}}``
        # dict, NOT a list of rows. The webapp consumer in
        # ``static/admin/js/desktops_status.js`` reads ``data.total`` and
        # ``data.status`` directly. Iterating ``for row in result`` looped
        # over the dict's keys (``"total"``, ``"status"``) and called
        # ``StatsGenericResponse(**"total")`` → 500.
        result = await asyncio.to_thread(AdminStatsService.get_desktops_stats)
        return StatsGenericResponse(**(result or {}))
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get desktop status statistics",
            traceback.format_exc(),
        )


@admin_router.get(
    "/stats/domains/status",
    tags=[tag],
    response_model=StatsDomainsStatusResponse,
    summary="Get domains status statistics",
    description="Returns domain statistics grouped by kind and status.",
    responses={500: {"model": ErrorResponse}},
)
async def stats_domains_status(request: Request):
    try:
        result = await asyncio.to_thread(AdminStatsService.get_domains_status)
        return StatsDomainsStatusResponse(**result)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get domains status statistics",
            traceback.format_exc(),
        )


@admin_router.get(
    "/stats/category/status",
    tags=[tag],
    summary="Get category status statistics",
    description="Returns category-level status statistics showing wrong-status desktops and templates.",
    response_model=StatsGenericResponse,
    responses={500: {"model": ErrorResponse}},
)
async def stats_category_status(request: Request) -> StatsGenericResponse:
    try:
        result = {
            "categories": await asyncio.to_thread(AdminStatsService.get_category_status)
        }
        return StatsGenericResponse(**result)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get category status statistics",
            traceback.format_exc(),
        )


# -----------------------------------------------------------------------------
# CATEGORY STATS — literal sub-paths MUST come before /stats/categories/{kind}
# and before the top-level /stats/{kind} catch-all.
# -----------------------------------------------------------------------------


@admin_router.get(
    "/stats/categories",
    tags=[tag],
    response_model=StatsCategoriesResponse,
    summary="Get grouped category statistics",
    description="Returns comprehensive statistics grouped by categories.",
    responses={500: {"model": ErrorResponse}},
)
async def stats_categories(request: Request):
    try:
        result = {
            "category": await asyncio.to_thread(
                AdminStatsService.get_group_by_categories
            )
        }
        return StatsCategoriesResponse(**result)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get category statistics",
            traceback.format_exc(),
        )


@admin_router.get(
    "/stats/categories/limits",
    tags=[tag],
    summary="Get category limits and hardware statistics",
    description="Returns category-level hardware limits and running resource statistics.",
    response_model=StatsGenericResponse,
    responses={500: {"model": ErrorResponse}},
)
async def stats_categories_limits(request: Request) -> StatsGenericResponse:
    try:
        result = {
            "category": await asyncio.to_thread(
                AdminStatsService.get_categories_limits_hardware
            )
        }
        return StatsGenericResponse(**result)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get category limits statistics",
            traceback.format_exc(),
        )


@admin_router.get(
    "/stats/categories/deployments",
    tags=[tag],
    response_model=StatsCategoriesDeploymentsResponse,
    summary="Get category deployments statistics",
    description="Returns deployment counts grouped by category.",
    responses={500: {"model": ErrorResponse}},
)
async def stats_categories_deployments(request: Request):
    try:
        result = {
            "categories": await asyncio.to_thread(
                AdminStatsService.get_categories_deployments
            )
        }
        return StatsCategoriesDeploymentsResponse(**result)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get category deployments statistics",
            traceback.format_exc(),
        )


@admin_router.get(
    "/stats/categories/{kind}/{state}",
    tags=[tag],
    response_model=StatsGenericResponse,
    summary="Get category statistics by kind and state",
    description="Returns category statistics for a specific kind and state.",
    responses={500: {"model": ErrorResponse}},
)
async def stats_categories_kind_state(
    request: Request, kind: Literal["desktop", "template"], state: str
) -> StatsGenericResponse:
    try:
        result = {
            "category": await asyncio.to_thread(
                AdminStatsService.get_categories_kind_state, kind, state
            )
        }
        return StatsGenericResponse(**result)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get category kind/state statistics",
            traceback.format_exc(),
        )


@admin_router.get(
    "/stats/categories/{kind}",
    tags=[tag],
    response_model=StatsGenericResponse,
    summary="Get category statistics by kind",
    description="Returns category statistics for a specific kind (desktop, template).",
    responses={500: {"model": ErrorResponse}},
)
async def stats_categories_kind(
    request: Request, kind: Literal["desktop", "template"]
) -> StatsGenericResponse:
    try:
        result = {
            "category": await asyncio.to_thread(
                AdminStatsService.get_categories_kind_state, kind
            )
        }
        return StatsGenericResponse(**result)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get category kind statistics",
            traceback.format_exc(),
        )


# -----------------------------------------------------------------------------
# Per-kind stats routes (replacing the former /stats/{kind} catch-all)
# -----------------------------------------------------------------------------


@admin_router.get(
    "/stats/users",
    tags=[tag],
    response_model=list[StatsKindUser],
    summary="Get user statistics",
    description="Returns a list of all users with their role, category and group.",
    responses={500: {"model": ErrorResponse}},
)
async def stats_users(request: Request):
    try:
        result = await asyncio.to_thread(AdminStatsService.get_kind, "users")
        return [StatsKindUser(**u) for u in result]
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get user statistics",
            traceback.format_exc(),
        )


@admin_router.get(
    "/stats/desktops",
    tags=[tag],
    response_model=list[StatsKindDesktop],
    summary="Get desktop statistics",
    description="Returns a list of all desktops with their owning user.",
    responses={500: {"model": ErrorResponse}},
)
async def stats_desktops(request: Request):
    try:
        result = await asyncio.to_thread(AdminStatsService.get_kind, "desktops")
        return [StatsKindDesktop(**d) for d in result]
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get desktop statistics",
            traceback.format_exc(),
        )


@admin_router.get(
    "/stats/templates",
    tags=[tag],
    response_model=list[StatsKindTemplate],
    summary="Get template statistics",
    description="Returns a list of all template IDs.",
    responses={500: {"model": ErrorResponse}},
)
async def stats_templates(request: Request):
    try:
        result = await asyncio.to_thread(AdminStatsService.get_kind, "templates")
        return [StatsKindTemplate(**t) for t in result]
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get template statistics",
            traceback.format_exc(),
        )


@admin_router.get(
    "/stats/hypervisors",
    tags=[tag],
    response_model=list[StatsKindHypervisor],
    summary="Get hypervisor statistics",
    description="Returns a list of all hypervisors with their status and only_forced flag.",
    responses={500: {"model": ErrorResponse}},
)
async def stats_hypervisors(request: Request):
    try:
        result = await asyncio.to_thread(AdminStatsService.get_kind, "hypervisors")
        return [StatsKindHypervisor(**h) for h in result]
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get hypervisor statistics",
            traceback.format_exc(),
        )


@admin_router.get(
    # NOTE: 3-segment path (under /api/v4/admin/domains/) cannot collide
    # with the 4-segment /admin/domains/{field}/{kind} catch-all declared
    # on manager_router (admin/domains.py) which is registered earlier
    # because manager_router < admin_router in include order.
    "/admin/domains/started-count",
    tags=[tag],
    summary="Get started domains count by category",
    description="Returns the count of started desktop domains grouped by category.",
    response_model=list[StatsGenericResponse],
    responses={500: {"model": ErrorResponse}},
)
async def admin_domains_started_count(
    request: Request,
) -> list[StatsGenericResponse]:
    try:
        result = await asyncio.to_thread(
            AdminStatsService.get_domains_by_category_count
        )
        return [StatsGenericResponse(**row) for row in (result or [])]
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get started domains count",
            traceback.format_exc(),
        )
