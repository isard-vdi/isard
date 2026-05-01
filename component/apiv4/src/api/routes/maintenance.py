#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Miriam Melina Gamboa Valdez
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later


import asyncio
import os
import traceback

from api import admin_router, maintenance_router, open_router
from api.schemas.common import EmptyResponse, ErrorResponse
from api.schemas.maintenance import (
    MaintenanceStatusResponse,
    MaintenanceStatusUpdate,
    MaintenanceTextGetResponse,
    MaintenanceTextResponse,
    MaintenanceTextUpdate,
)
from api.services.error import Error
from api.services.maintenance import MaintenanceService
from cachetools import TTLCache, cached
from fastapi import Depends, Request
from fastapi.responses import JSONResponse, Response

tag = "maintenance"

# Named caches: short TTL is mainly thundering-herd protection during
# global maintenance toggles, but writers (admin endpoints further down
# this module) should still drop them so the next read sees the new
# state instead of a 5 s stale window.
maintenance_status_cache: TTLCache = TTLCache(maxsize=1, ttl=5)
get_maintenance_cache: TTLCache = TTLCache(maxsize=1, ttl=5)


def clear_maintenance_caches() -> None:
    """Invalidate both maintenance read caches after a status flip."""
    maintenance_status_cache.clear()
    get_maintenance_cache.clear()


@cached(cache=maintenance_status_cache)
@open_router.get(
    "/maintenance/status",
    tags=[tag],
    summary="Get Maintenance Status",
    description="Returns the current global maintenance status of the API.",
    response_model=MaintenanceStatusResponse,
    responses={500: {"model": ErrorResponse}},
)
async def maintenance_status(request: Request):
    try:
        return MaintenanceStatusResponse(
            enabled=await asyncio.to_thread(MaintenanceService.is_enabled)
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve global maintenance status",
            traceback.format_exc(),
        )


@open_router.get(
    "/maintenance/text/frontend",
    tags=[tag],
    summary="Get maintenance text for frontend",
    description="Returns the current maintenance text for frontend display.",
    response_model=MaintenanceTextResponse,
    responses={500: {"model": ErrorResponse}, 204: {"model": None}},
)
async def get_maintenance_text_frontend(request: Request):
    try:
        if await asyncio.to_thread(MaintenanceService.is_enabled):
            text = await asyncio.to_thread(MaintenanceService.get_text)
            return MaintenanceTextResponse(**text)
        else:
            return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve maintenance text for frontend",
            traceback.format_exc(),
        )


@cached(cache=get_maintenance_cache)
@maintenance_router.get(
    "/maintenance",
    tags=[tag],
    summary="Get maintenance",
    description="Returns the current maintenance status of the API considering the user role and category.",
    response_model=MaintenanceStatusResponse,
    responses={500: {"model": ErrorResponse}},
)
async def get_maintenance(request: Request):
    try:
        if request.token_payload["role_id"] == "admin":
            # Admins should not be affected by maintenance
            return MaintenanceStatusResponse(enabled=False)
        status = await asyncio.to_thread(MaintenanceService.is_enabled)
        category_status = await asyncio.to_thread(
            MaintenanceService.get_category_status, request.token_payload["category_id"]
        )
        return MaintenanceStatusResponse(enabled=status or category_status)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve maintenance status",
            traceback.format_exc(),
        )


@admin_router.get(
    "/maintenance/text",
    tags=[tag],
    summary="Get maintenance text",
    description="Returns the current maintenance text.",
    response_model=MaintenanceTextGetResponse,
    responses={500: {"model": ErrorResponse}},
)
async def get_maintenance_text(request: Request):
    try:
        text = await asyncio.to_thread(MaintenanceService.get_text)
        return MaintenanceTextGetResponse(text=text)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve maintenance text",
            traceback.format_exc(),
        )


@admin_router.get(
    "/maintenance/{category_id}",
    tags=[tag],
    summary="Get category maintenance status",
    description="Returns the maintenance status for a specific category. Admin only.",
    response_model=MaintenanceStatusResponse,
    responses={500: {"model": ErrorResponse}},
)
async def get_category_maintenance(request: Request, category_id: str):
    try:
        global_status = await asyncio.to_thread(MaintenanceService.is_enabled)
        category_status = await asyncio.to_thread(
            MaintenanceService.get_category_status, category_id
        )
        return MaintenanceStatusResponse(enabled=global_status or category_status)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve category maintenance status",
            traceback.format_exc(),
        )


# Admin-only. Maintenance management endpoints


@admin_router.put(
    "/maintenance",
    tags=[tag],
    summary="Update maintenance status",
    description="Updates the maintenance status of the API.",
    response_model=MaintenanceStatusResponse,
    responses={500: {"model": ErrorResponse}},
)
async def update_maintenance(
    request: Request,
    status: MaintenanceStatusUpdate,
):
    try:
        await asyncio.to_thread(MaintenanceService.set_enabled, status.enabled)
        return MaintenanceStatusResponse(
            enabled=await asyncio.to_thread(MaintenanceService.is_enabled)
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to update maintenance status",
            traceback.format_exc(),
        )


@admin_router.put(
    "/maintenance/text",
    tags=[tag],
    summary="Update maintenance text",
    description="Updates the maintenance text displayed to users.",
    response_model=EmptyResponse,
    responses={503: {"model": ErrorResponse}, 500: {"model": ErrorResponse}},
)
async def update_maintenance_text(
    request: Request,
    text: MaintenanceTextUpdate,
):
    try:
        await asyncio.to_thread(MaintenanceService.update_text, text)
        return EmptyResponse()
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to update maintenance text",
            traceback.format_exc(),
        )
