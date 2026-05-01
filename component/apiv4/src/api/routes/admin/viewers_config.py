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
from typing import Literal

from api import admin_router
from api.schemas.admin.viewers_config import ViewerConfigUpdateRequest
from api.schemas.common import EmptyResponse, ErrorResponse
from api.services.admin.viewers_config import AdminViewersConfigService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse

tag = "admin-viewers-config"


# ══════════════════════════════════════════════════════════════════════════
#  Viewers Configuration
# ══════════════════════════════════════════════════════════════════════════


@admin_router.get(
    "/admin/viewers-config",
    tags=[tag],
    response_model=list[dict],
    summary="Get viewers configuration",
    description="Returns all viewers configurations as a list — one entry"
    " per viewer (``file_rdpgw``, ``file_rdpvpn``, ``file_spice``) with"
    " ``key``, ``viewer``, ``custom``, ``default``, ``fixed`` fields."
    " Webapp DataTables consumes the response root as the row array.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_viewers_config(request: Request) -> list[dict]:
    try:
        return AdminViewersConfigService.get_viewers_config() or []
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get viewers configuration",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/viewers-config/{viewer}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update viewer configuration",
    description="Updates the custom configuration for a specific viewer.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_viewers_config_update(
    request: Request,
    viewer: Literal["file_rdpgw", "file_rdpvpn", "file_spice"],
    data: ViewerConfigUpdateRequest,
):
    try:
        AdminViewersConfigService.update_viewers_config(viewer, data.custom)
        return {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update viewer configuration",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/viewers-config/reset/{viewer}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Reset viewer configuration",
    description="Resets a viewer custom configuration to its default. "
    "Valid viewers: file_rdpgw, file_rdpvpn, file_spice.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_viewers_config_reset(
    request: Request, viewer: Literal["file_rdpgw", "file_rdpvpn", "file_spice"]
):
    try:
        AdminViewersConfigService.reset_viewers_config(viewer)
        return {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to reset viewer configuration",
            traceback.format_exc(),
        )
