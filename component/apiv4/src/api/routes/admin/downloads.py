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
from typing import Optional

from api import admin_router
from api.schemas.admin.downloads import DownloadItem, DownloadsOverviewResponse
from api.schemas.common import EmptyResponse, ErrorResponse
from api.services.admin.downloads import AdminDownloadsService
from api.services.error import Error
from fastapi import Body, Path, Request
from fastapi.responses import JSONResponse

tag = "admin_downloads"


# =============================================================================
# DOWNLOADS OVERVIEW
# =============================================================================


@admin_router.get(
    "/admin/downloads",
    tags=[tag],
    response_model=DownloadsOverviewResponse,
    summary="Get downloads overview",
    description="Get an overview of available downloads. Requires registration.",
    responses={
        428: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_downloads(request: Request) -> DownloadsOverviewResponse:
    try:
        # AdminDownloadsService.get_downloads() makes a synchronous HTTP
        # call to the upstream updates server (``requests`` with a 10s
        # timeout). Offload to the threadpool so a slow upstream
        # doesn't freeze the apiv4 event loop for every other client.
        await asyncio.to_thread(AdminDownloadsService.get_downloads)
        return DownloadsOverviewResponse()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get downloads",
            traceback.format_exc(),
        )


# =============================================================================
# DOWNLOADS BY KIND
# =============================================================================


@admin_router.get(
    "/admin/downloads/{kind}",
    tags=[tag],
    response_model=list[DownloadItem],
    summary="Get downloads by kind",
    description="Get available downloads for a specific kind (domains, media, virt_install, videos, viewers).",
    responses={
        428: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_downloads_kind(
    request: Request,
    kind: str = Path(
        ..., description="Download kind: domains, media, virt_install, videos, viewers"
    ),
) -> list[DownloadItem]:
    try:
        # See ``admin_downloads`` above: this also calls the updates
        # server synchronously and must not block the event loop.
        result = await asyncio.to_thread(
            AdminDownloadsService.get_downloads_kind,
            kind,
            request.token_payload["user_id"],
        )
        return [DownloadItem(**row) for row in (result or [])]
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get downloads by kind",
            traceback.format_exc(),
        )


# =============================================================================
# REGISTRATION
# =============================================================================


@admin_router.post(
    "/admin/downloads/register",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Register with updates server",
    description="Register this IsardVDI instance with the updates server.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_downloads_register(request: Request):
    try:
        # ``register()`` POSTs to the updates server synchronously.
        await asyncio.to_thread(AdminDownloadsService.register)
        return EmptyResponse()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to register",
            traceback.format_exc(),
        )


# =============================================================================
# DOWNLOAD ACTIONS
# =============================================================================


@admin_router.post(
    "/admin/downloads/{action}/{kind}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Execute download action for all items",
    description="Execute a download action (download, abort, delete) for all new items of a kind.",
    responses={
        428: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_downloads_action(
    request: Request,
    action: str = Path(..., description="Action: download, abort, delete"),
    kind: str = Path(..., description="Download kind"),
):
    try:
        # ``download_action`` enqueues storage chains and may probe the
        # updates server synchronously — same threadpool offload as the
        # other download endpoints.
        await asyncio.to_thread(
            AdminDownloadsService.download_action,
            action,
            kind,
            request.token_payload["user_id"],
        )
        return EmptyResponse()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to execute download action",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/downloads/{action}/{kind}/{id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Execute download action for a specific item",
    description="Execute a download action (download, abort, delete) for a specific item.",
    responses={
        428: {"model": ErrorResponse},
        504: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_downloads_action_id(
    request: Request,
    action: str = Path(..., description="Action: download, abort, delete"),
    kind: str = Path(..., description="Download kind"),
    id: str = Path(..., description="Item ID"),
    body: Optional[dict] = Body(default=None),
):
    try:
        # Same threadpool offload as the no-id variant; the registry
        # download path also calls Storage / Scheduler synchronously.
        await asyncio.to_thread(
            AdminDownloadsService.download_action,
            action,
            kind,
            request.token_payload["user_id"],
            id=id,
            data=body,
        )
        return EmptyResponse()
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to execute download action",
            traceback.format_exc(),
        )
