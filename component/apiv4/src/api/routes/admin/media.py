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

from api import manager_router
from api.dependencies.alloweds import owns_domain_id, owns_media_id
from api.schemas.admin.media import AdminMediaItem, AdminMediaStatusCount
from api.schemas.common import ErrorResponse, SimpleResponse
from api.schemas.media import DesktopAttachedMediaItem, MediaCheckResponse
from api.services.admin.media import AdminMediaService
from api.services.error import Error
from api.services.media import MediaService
from fastapi import Depends, Path, Request
from fastapi.responses import JSONResponse

tag = "admin_media"


# =============================================================================
# MEDIA STATUS
# =============================================================================


@manager_router.get(
    "/admin/item/media/status",
    tags=[tag],
    response_model=list[AdminMediaStatusCount],
    summary="Get media status counts",
    description="Get counts of media items grouped by status. "
    "Managers are scoped to their category.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_media_status(request: Request):
    try:
        result = await asyncio.to_thread(
            AdminMediaService.get_media_status, request.token_payload
        )
        return JSONResponse(
            content=[
                AdminMediaStatusCount(**row).model_dump(mode="json")
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
            "Failed to get media status",
            traceback.format_exc(),
        )


# =============================================================================
# MEDIA LISTING
# =============================================================================


@manager_router.get(
    "/admin/items/media",
    tags=[tag],
    response_model=list[AdminMediaItem],
    summary="Get all media",
    description="Get all media items. Admins see all; managers are scoped to their category.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_media_list(request: Request):
    try:
        result = await asyncio.to_thread(
            AdminMediaService.get_media, request.token_payload
        )
        return JSONResponse(
            content=[
                AdminMediaItem(**row).model_dump(mode="json") for row in (result or [])
            ],
            status_code=200,
        )
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
    "/admin/items/media/{status}",
    tags=[tag],
    response_model=list[AdminMediaItem],
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
        result = await asyncio.to_thread(
            AdminMediaService.get_media, request.token_payload, status=status
        )
        return JSONResponse(
            content=[
                AdminMediaItem(**row).model_dump(mode="json") for row in (result or [])
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get media by status",
            traceback.format_exc(),
        )


# =============================================================================
# MEDIA — admin/manager operations on individual media items
# (paths kept under /item/... to stay wire-compatible with both
#  Vue 2 and Vue 3 callers; only the file location changed.)
# =============================================================================


@manager_router.get(
    "/admin/item/desktop/{desktop_id}/media-list",
    tags=[tag],
    response_model=list[DesktopAttachedMediaItem],
    summary="List media attached to a desktop",
    description=(
        "Returns the list of media items (isos + floppies) currently attached "
        "to the given desktop's hardware configuration. Used to populate the "
        "hotplug modal in the webapp admin. Admin/manager only — matches v3 "
        "``POST /desktops/media_list`` ``@is_admin_or_manager``."
    ),
    dependencies=[Depends(owns_domain_id("desktop_id"))],
)
async def list_desktop_attached_media(request: Request, desktop_id: str):
    try:
        media = await asyncio.to_thread(
            MediaService.list_desktop_attached_media, desktop_id
        )
        return JSONResponse(
            content=[
                DesktopAttachedMediaItem(**m).model_dump(mode="json") for m in media
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve media list for desktop {desktop_id}",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/item/media/{media_id}/change-owner/{user_id}",
    summary="Change media owner",
    tags=[tag],
    response_model=SimpleResponse,
    description=(
        "Reassigns a media item to a different user. ``@is_admin_or_manager``. "
        "Both ``ownsUserId(user_id)`` and ``ownsMediaId(media_id)`` are "
        "enforced by the service."
    ),
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def change_media_owner(
    request: Request,
    media_id: str = Path(..., description="The ID of the media"),
    user_id: str = Path(..., description="The ID of the new owner"),
):
    try:
        await asyncio.to_thread(
            MediaService.change_owner,
            payload=request.token_payload,
            media_id=media_id,
            new_user_id=user_id,
        )
        return JSONResponse(
            content=SimpleResponse(id=media_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to change media owner",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/item/media/{media_id}/check",
    summary="Check media file existence on disk",
    tags=[tag],
    response_model=MediaCheckResponse,
    description=(
        "Schedules a background task that verifies the media file on disk. "
        "If the media is not currently downloaded its status is forced to "
        "``deleted``. Otherwise an RQ ``check_media_existence`` task is "
        "enqueued against the storage pool that owns the file. Admin/manager "
        "only — matches v3 ``PUT /media/check/{id}`` ``@is_admin_or_manager``."
    ),
)
async def check_media(request: Request, media_id=Depends(owns_media_id)):
    try:
        result = await asyncio.to_thread(
            MediaService.check_media_existence,
            media_id,
            request.token_payload["user_id"],
        )
        return JSONResponse(
            content=MediaCheckResponse(**(result or {})).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to check media existence",
            traceback.format_exc(),
        )
