#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import json
import traceback

from api import admin_router
from api.schemas.common import ErrorResponse
from api.services.admin_socketio import AdminSocketioService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse

tag = "admin_socketio"


# =============================================================================
# SOCKETIO EMIT ENDPOINTS (admin_router)
# =============================================================================


@admin_router.post(
    "/admin/socketio",
    tags=[tag],
    summary="Emit socketio events",
    description="Sends one or more socketio events. Expects a JSON array of event objects.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_emit_socketio(request: Request):
    try:
        try:
            events = await request.json()
        except json.JSONDecodeError:
            raise Error("bad_request", "Request body must be JSON")
        if not isinstance(events, list):
            raise await Error.create(
                request,
                "bad_request",
                "JSON array expected",
            )
        AdminSocketioService.emit_events(events)
        return JSONResponse(content=True, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to emit socketio events",
            traceback.format_exc(),
        )
