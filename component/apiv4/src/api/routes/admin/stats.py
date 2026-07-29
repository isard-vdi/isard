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
import logging
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

log = logging.getLogger(__name__)

tag = "admin_stats"


def _stats_rows(
    rows: list[dict] | None,
    required: tuple[str, ...],
    optional: tuple[str, ...] = (),
) -> list[dict]:
    """Project plucked inventory rows onto their schema's wire shape.

    Building one Pydantic model per row and ``model_dump(mode="json")``-ing
    it only to hand the result to ``JSONResponse`` encodes the whole
    inventory twice, inline on the event loop. Pass ``required``/``optional``
    in schema declaration order so the projection stays byte-identical, and
    keep the two invariants the round-trip provided:

    * ``None`` never reaches the wire. The Go stats collector's ogen-
      generated ``OptString`` decodes "absent" vs "present", not ``null``,
      so a null field fails it with ``unexpected byte 110 'n'``. Orphan
      rows — a deleted user document whose vpn config still exists — are
      what carry those nulls (see the schema comment on ``StatsKindUser``).
    * Rows short of a required value are dropped, not emitted incomplete:
      the client's decoder would reject the entire payload, not the row.
    """
    projected = []
    dropped = 0
    for row in rows or []:
        if any(row.get(key) is None for key in required):
            dropped += 1
            continue
        item = {key: row[key] for key in required}
        item.update({key: row[key] for key in optional if row.get(key) is not None})
        projected.append(item)
    if dropped:
        # Previously an incomplete row failed the whole response, which was at
        # least visible. Dropping it must not be silent: from the collector's
        # side the item simply stops existing.
        log.warning(
            "stats_inventory_rows_dropped count=%d required=%s", dropped, required
        )
    return projected


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
        return JSONResponse(
            content=_stats_rows(result, ("id",), ("role", "category", "group")),
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
            content=_stats_rows(result, ("id", "user")),
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
            content=_stats_rows(result, ("id",)),
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
            content=_stats_rows(result, ("id", "status", "only_forced")),
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
