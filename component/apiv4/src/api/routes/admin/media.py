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

from api import manager_router
from api.schemas.common import ErrorResponse
from api.services.admin_media import AdminMediaService
from api.services.error import Error
from fastapi import Path, Request
from fastapi.responses import JSONResponse

tag = "admin_media"


# =============================================================================
# MEDIA STATUS
# =============================================================================


@manager_router.get(
    "/media/status",
    tags=[tag],
    summary="Get media status counts",
    description="Get counts of media items grouped by status. "
    "Managers are scoped to their category.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_media_status(request: Request):
    try:
        result = AdminMediaService.get_media_status(request.token_payload)
        return result
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get media status",
            traceback.format_exc(),
        )


# =============================================================================
# MEDIA LISTING
# =============================================================================


@manager_router.get(
    "/admin/media",
    tags=[tag],
    summary="Get all media",
    description="Get all media items. Admins see all; managers are scoped to their category.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_media_list(request: Request):
    try:
        result = AdminMediaService.get_media(request.token_payload)
        return result
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get media",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/media/{status}",
    tags=[tag],
    summary="Get media by status",
    description="Get media items filtered by status. "
    "Admins see all; managers are scoped to their category.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_media_by_status(
    request: Request,
    status: str = Path(..., description="Media status to filter by"),
):
    try:
        result = AdminMediaService.get_media(request.token_payload, status=status)
        return result
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get media by status",
            traceback.format_exc(),
        )
