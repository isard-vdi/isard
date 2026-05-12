#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import traceback

from api import admin_router
from api.schemas.admin.notify import (
    AdminNotifyDesktopsQueueRequest,
    NotifyDesktopRequest,
    NotifyUserDesktopRequest,
)
from api.schemas.common import EmptyResponse, ErrorResponse
from api.services.admin.notify import AdminNotifyService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse, Response

tag = "admin_notify"


# =============================================================================
# NOTIFY ENDPOINTS (admin_router)
# =============================================================================


@admin_router.post(
    "/admin/notify/user/desktop",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Notify user about desktop",
    description="Sends a notification to a user about a desktop event.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_notify_user_desktop(request: Request, data: NotifyUserDesktopRequest):
    try:
        await asyncio.to_thread(
            AdminNotifyService.notify_user_desktop,
            data.user_id,
            data.type,
            data.msg_code,
            data.params,
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to notify user",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/notify/desktop",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Notify a desktop",
    description="Sends a notification to a desktop.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_notify_desktop(request: Request, data: NotifyDesktopRequest):
    try:
        await asyncio.to_thread(
            AdminNotifyService.notify_desktop,
            data.desktop_id,
            data.type,
            data.msg_code,
            data.params,
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to notify desktop",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/notify/desktops/queue/{hyp_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Notify desktop queue",
    description="Parses desktop queues for a hypervisor and notifies affected users.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_notify_desktop_queue(
    request: Request,
    hyp_id: str,
    data: AdminNotifyDesktopsQueueRequest,
):
    try:
        await asyncio.to_thread(
            AdminNotifyService.notify_desktop_queue, data.root, hyp_id
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to notify desktop queue",
            traceback.format_exc(),
        )
