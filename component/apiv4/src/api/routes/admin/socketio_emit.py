#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import traceback

from api import admin_router
from api.schemas.admin.notify import AdminSocketioEmitRequest
from api.schemas.common import ErrorResponse
from api.services.admin.socketio import AdminSocketioService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse, Response

tag = "admin_socketio"


# =============================================================================
# SOCKETIO EMIT ENDPOINTS (admin_router)
# =============================================================================


@admin_router.post(
    "/admin/items/socketio",
    tags=[tag],
    status_code=204,
    response_class=Response,
    summary="Emit socketio events",
    description="Sends one or more socketio events. Expects a JSON array of event objects.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_emit_socketio(request: Request, data: AdminSocketioEmitRequest):
    try:
        await asyncio.to_thread(AdminSocketioService.emit_events, data.root)
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to emit socketio events",
            traceback.format_exc(),
        )
