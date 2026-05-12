#
#   Copyright © 2025 Naomi Hidalgo Piñar, Miriam Melina Gamboa Valdez
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
from typing import Literal, Optional

from api import advanced_router, token_router
from api.dependencies.alloweds import owns_media_id
from api.schemas.allowed import AllowedResponse, AllowedUpdate
from api.schemas.common import DeleteResponse, ErrorResponse, SimpleResponse
from api.schemas.media import (
    CreateMediaRequest,
    MediaDesktopResponse,
    MediaInstallItem,
    MediaQuotaCheckResponse,
    MediaResponse,
    UserAllowedMediaPaginationResponse,
    UserAllowedMediaSearchFields,
    UserMediaResponse,
    UserSharedMediaResponse,
    VirtInstallListResponse,
)
from api.services.error import Error
from api.services.media import MediaService
from fastapi import Depends, Path, Query, Request
from fastapi.responses import JSONResponse, Response
from isardvdi_common.helpers.quotas import Quotas

tag = "media"


@token_router.get(
    "/item/media/{media_id}",
    response_model=MediaResponse,
    tags=[tag],
    summary="Get details of a media",
    description="Returns a media in IsardVDI based on an ID.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_media(request: Request, media_id=Depends(owns_media_id)):
    media = await asyncio.to_thread(MediaService.get_media, media_id)
    try:
        return JSONResponse(
            content=MediaResponse(**media).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve media",
            traceback.format_exc(),
        )


@advanced_router.get(
    "/items/media/installs",
    tags=[tag],
    response_model=VirtInstallListResponse,
    summary="Get available OS templates for media installs",
    description="Returns the list of available OS templates (virt_install) that can be used when creating a desktop from media.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_media_installs(request: Request):
    try:
        return JSONResponse(
            content=VirtInstallListResponse(
                installs=MediaService.get_media_installs(),
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error as e:
        raise e
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve media installs",
            traceback.format_exc(),
        )


@token_router.get(
    "/items/media",
    summary="Get user's media files",
    tags=[tag],
    response_model=UserMediaResponse,
    description=(
        "Returns a list of media files belonging to the calling user. "
        "``@has_token`` — the service filters by ``user_id`` so any "
        "logged-in user can call it."
    ),
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_user_media(request: Request):
    try:
        return JSONResponse(
            content=UserMediaResponse(
                media=await asyncio.to_thread(
                    MediaService.get_user_media, request.token_payload["user_id"]
                ),
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve user media",
            traceback.format_exc(),
        )


@token_router.get(
    "/items/media/get-shared",
    tags=[tag],
    response_model=UserSharedMediaResponse,
    summary="Get shared media for user",
    description="Returns a list of all media that are shared with them.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_user_shared_media(
    request: Request,
):
    try:
        return JSONResponse(
            content=UserSharedMediaResponse(
                media=await asyncio.to_thread(
                    MediaService.get_user_shared_media, request.token_payload
                ),
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user shared media",
            traceback.format_exc(),
        )


@token_router.get(
    "/items/media/get-allowed",
    tags=[tag],
    response_model=UserAllowedMediaPaginationResponse,
    summary="Get allowed media for user",
    description="Returns a list of all media that the user can see, considering its role permissions.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_user_allowed_media(
    request: Request,
    start_after: int = Query(
        default=None,
        description="Start the retrieval after the given accessed. If not provided, starts from the beginning.",
    ),
    page_size: int = Query(
        default=10,
        description="Number of media to return. Default is 10. The given value will be multiplied by 5 in order to preload more media for the user.",
        ge=1,
        le=50,
    ),
    sort_field: Literal["accessed"] = Query(
        default="accessed",
        description="Field to sort the media by. Default is 'accessed'.",
    ),
    sort_order: Literal["desc", "asc"] = Query(
        default="desc",
        description="Order to sort the media by. Default is 'desc'. Can be 'asc' or 'desc'.",
    ),
    search: str = Query(
        default=None,
        description="Search term to filter media by name or description. If provided, search_field must also be provided.",
    ),
    search_field: Optional[UserAllowedMediaSearchFields] = Query(
        default=None,
        description="Field to search in. If not provided, no search is performed.",
    ),
):
    try:
        if search and not search_field:
            raise Error(
                "bad_request",
                "search_field must be provided when search is set",
                traceback.format_exc(),
            )
        if search_field and not search:
            raise Error(
                "bad_request",
                "search must be provided when search_field is set",
                traceback.format_exc(),
            )
        user_media = await asyncio.to_thread(
            MediaService.get_user_allowed_media,
            user_id=request.token_payload["user_id"],
            user_category=request.token_payload["category_id"],
            user_group=request.token_payload["group_id"],
            user_role=request.token_payload.get("role_id"),
            start_after=start_after,
            page_size=page_size,
            sort_field=sort_field,
            sort_order=sort_order,
            search=search,
            search_field=search_field,
        )
        return JSONResponse(
            content=UserAllowedMediaPaginationResponse(**user_media).model_dump(
                mode="json"
            ),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user allowed media",
            traceback.format_exc(),
        )


@advanced_router.get(
    "/item/media/{media_id}/get-allowed",
    summary="Get allowed users, roles, groups, categories for a media item",
    tags=[tag],
    response_model=AllowedResponse,
    description="Returns allowed users, roles, groups, categories for a media item.",
    dependencies=[Depends(owns_media_id)],
)
async def get_media_allowed_table(request: Request, media_id: str):
    try:
        return JSONResponse(
            content=AllowedResponse(
                **await asyncio.to_thread(
                    MediaService.get_media_allowed,
                    media_id,
                    request.token_payload["category_id"],
                )
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve allowed table for media",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/item/media/{media_id}/update-allowed",
    tags=[tag],
    response_model=SimpleResponse,
    summary="Update allowed users, roles, groups, categories for a media item",
    description="Update the list of groups, users, roles, and categories that have access to the specified media item. Only provided fields will be updated.",
    dependencies=[Depends(owns_media_id)],
)
async def update_media_allowed(request: Request, allowed: AllowedUpdate, media_id: str):
    try:
        await asyncio.to_thread(MediaService.update_media_allowed, media_id, allowed)
        return JSONResponse(
            content=SimpleResponse(id=media_id).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to update media allowed entities",
            traceback.format_exc(),
        )


@token_router.get(
    "/item/media/{media_id}/get-desktops",
    summary="Get desktops using a media item",
    tags=[tag],
    response_model=list[MediaDesktopResponse],
    description="Returns a list of desktops using the given media item.",
)
async def get_media_desktops(request: Request, media_id=Depends(owns_media_id)):
    try:
        return JSONResponse(
            content=[
                MediaDesktopResponse(**desktop).model_dump(mode="json")
                for desktop in await asyncio.to_thread(
                    MediaService.get_media_desktops, media_id
                )
            ],
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve desktops for media",
            traceback.format_exc(),
        )


@advanced_router.delete(
    "/item/media/{media_id}",
    summary="Delete a media item",
    tags=[tag],
    response_model=DeleteResponse,
    description=(
        "Deletes a media item and returns the task ID. ``@is_not_user`` — "
        "ownership is enforced by ``owns_media_id``."
    ),
    responses={
        202: {"model": DeleteResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def delete_media(
    request: Request, response: Response, media_id=Depends(owns_media_id)
):
    try:
        task_id = await asyncio.to_thread(
            MediaService.delete_media,
            media_id,
            request.token_payload,
        )
        if task_id is None:
            return JSONResponse(
                content=DeleteResponse(
                    message="Media deleted", message_code="item.deleted"
                ).model_dump(mode="json"),
                status_code=200,
            )

        return JSONResponse(
            content=DeleteResponse(
                message="Task to delete media queued",
                message_code="item.queued",
                tasks_ids=[task_id],
            ).model_dump(mode="json"),
            status_code=202,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to delete media",
            traceback.format_exc(),
        )


@advanced_router.post(
    "/item/media",
    summary="Create a new media item",
    tags=[tag],
    response_model=SimpleResponse,
    status_code=201,
    description="Creates a new media item. Returns the created media ID on success.",
    responses={
        201: {"description": "Media created successfully"},
        400: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_media(media_data: CreateMediaRequest, request: Request):
    """Create a new media item."""
    try:
        # ``MediaService.create_media`` is synchronous: it probes the
        # source URL with ``requests`` and runs several RethinkDB
        # writes. Calling it directly from an ``async def`` handler
        # blocks the apiv4 event loop for the full duration of the
        # probe — a slow upstream (archive.org, mirrors) wedges every
        # other in-flight request behind it. Offload to the default
        # threadpool so the event loop stays free.
        media_id = await asyncio.to_thread(
            MediaService.create_media, media_data, request.token_payload
        )
        return JSONResponse(
            content=SimpleResponse(id=str(media_id)).model_dump(mode="json"),
            status_code=201,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to create media",
            traceback.format_exc(),
        )


# NOTE: admin media listing lives at ``GET /admin/items/media/{status}`` on
# ``manager_router`` in ``routes/admin/media.py``.


@advanced_router.put(
    "/item/media/{media_id}/abort",
    summary="Abort a media download",
    tags=[tag],
    response_model=SimpleResponse,
    description=(
        "Aborts a media download. ``@is_not_user`` — ownership is "
        "enforced by ``owns_media_id``."
    ),
)
async def abort_media_download(request: Request, media_id=Depends(owns_media_id)):
    try:
        await asyncio.to_thread(MediaService.abort_media_download, media_id)
        return JSONResponse(
            content=SimpleResponse(id=media_id).model_dump(mode="json"), status_code=200
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to abort media download",
            traceback.format_exc(),
        )


@advanced_router.put(
    "/item/media/{media_id}/download",
    summary="Start a media download",
    tags=[tag],
    response_model=SimpleResponse,
    description=(
        "Starts a media download. ``@is_not_user`` — ownership is "
        "enforced by ``owns_media_id``."
    ),
)
async def start_media_download(request: Request, media_id=Depends(owns_media_id)):
    """Start a media download."""
    try:
        await asyncio.to_thread(MediaService.start_media_download, media_id)
        return JSONResponse(
            content=SimpleResponse(id=media_id).model_dump(mode="json"), status_code=200
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to start media download",
            traceback.format_exc(),
        )
