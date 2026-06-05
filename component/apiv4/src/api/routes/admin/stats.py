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


@admin_router.get(
    "/admin/item/stats/desktops/status",
    tags=[tag],
    summary="Get desktop status statistics",
    description="Returns desktop statistics grouped by status.",
    response_model=StatsGenericResponse,
    responses={500: {"model": ErrorResponse}},
)
async def stats_desktops_status(request: Request):
    try:
        # Service returns a single ``{"total": int, "status": {<status>: int}}``
        # dict, NOT a list of rows. The webapp consumer in
        # ``static/admin/js/desktops_status.js`` reads ``data.total`` and
        # ``data.status`` directly. Iterating ``for row in result`` looped
        # over the dict's keys (``"total"``, ``"status"``) and called
        # ``StatsGenericResponse(**"total")`` → 500.
        result = await asyncio.to_thread(AdminStatsService.get_desktops_stats)
        return JSONResponse(
            content=StatsGenericResponse(**(result or {})).model_dump(mode="json"),
            status_code=200,
        )
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
    "/admin/item/stats/domains/status",
    tags=[tag],
    response_model=StatsDomainsStatusResponse,
    summary="Get domains status statistics",
    description="Returns domain statistics grouped by kind and status.",
    responses={500: {"model": ErrorResponse}},
)
async def stats_domains_status(request: Request):
    try:
        result = await asyncio.to_thread(AdminStatsService.get_domains_status)
        return JSONResponse(
            content=StatsDomainsStatusResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
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
    "/admin/item/stats/categories",
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
        return JSONResponse(
            content=StatsCategoriesResponse(**result).model_dump(mode="json"),
            status_code=200,
        )
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
    "/admin/item/stats/categories/deployments",
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
        return JSONResponse(
            content=StatsCategoriesDeploymentsResponse(**result).model_dump(
                mode="json"
            ),
            status_code=200,
        )
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
    "/admin/items/stats/users",
    tags=[tag],
    response_model=list[StatsKindUser],
    summary="Get user statistics",
    description="Returns a list of all users with their role, category and group.",
    responses={500: {"model": ErrorResponse}},
)
async def stats_users(request: Request):
    try:
        result = await asyncio.to_thread(AdminStatsService.get_kind, "users")
        # ``role``/``category``/``group`` are ``Optional[str]`` so the
        # Pydantic schema accepts orphan rows whose user document was
        # deleted but whose vpn config still exists (see the schema
        # comment in api/schemas/admin/stats.py). Serialising them as
        # `"role": null` makes the Go stats-go collector's ogen-
        # generated `OptString.Decode` fail with `unexpected byte 110
        # 'n'` because ogen's `OptString` only handles "absent" vs
        # "present", not "null". Omit None fields so the wire shape
        # matches what `OptString` can decode.
        return JSONResponse(
            content=[
                StatsKindUser(**u).model_dump(mode="json", exclude_none=True)
                for u in result
            ],
            status_code=200,
        )
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
    "/admin/items/stats/desktops",
    tags=[tag],
    response_model=list[StatsKindDesktop],
    summary="Get desktop statistics",
    description="Returns a list of all desktops with their owning user.",
    responses={500: {"model": ErrorResponse}},
)
async def stats_desktops(request: Request):
    try:
        result = await asyncio.to_thread(AdminStatsService.get_kind, "desktops")
        return JSONResponse(
            content=[StatsKindDesktop(**d).model_dump(mode="json") for d in result],
            status_code=200,
        )
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
    "/admin/items/stats/templates",
    tags=[tag],
    response_model=list[StatsKindTemplate],
    summary="Get template statistics",
    description="Returns a list of all template IDs.",
    responses={500: {"model": ErrorResponse}},
)
async def stats_templates(request: Request):
    try:
        result = await asyncio.to_thread(AdminStatsService.get_kind, "templates")
        return JSONResponse(
            content=[StatsKindTemplate(**t).model_dump(mode="json") for t in result],
            status_code=200,
        )
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
    "/admin/items/stats/hypervisors",
    tags=[tag],
    response_model=list[StatsKindHypervisor],
    summary="Get hypervisor statistics",
    description="Returns a list of all hypervisors with their status and only_forced flag.",
    responses={500: {"model": ErrorResponse}},
)
async def stats_hypervisors(request: Request):
    try:
        result = await asyncio.to_thread(AdminStatsService.get_kind, "hypervisors")
        return JSONResponse(
            content=[StatsKindHypervisor(**h).model_dump(mode="json") for h in result],
            status_code=200,
        )
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
    # NOTE: this 4-segment path (under /api/v4/admin/items/domains/) cannot
    # collide with the 4-segment /admin/items/domains/{field}/{kind} catch-all
    # declared on manager_router (admin/domains.py) which is registered
    # earlier because manager_router < admin_router in include order.
    "/admin/items/domains/started-count",
    tags=[tag],
    summary="Get started domains count by category",
    description="Returns the count of started desktop domains grouped by category.",
    response_model=list[StatsGenericResponse],
    responses={500: {"model": ErrorResponse}},
)
async def admin_domains_started_count(
    request: Request,
):
    try:
        result = await asyncio.to_thread(
            AdminStatsService.get_domains_by_category_count
        )
        return JSONResponse(
            content=[
                StatsGenericResponse(**row).model_dump(mode="json")
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
            "Failed to get started domains count",
            traceback.format_exc(),
        )
