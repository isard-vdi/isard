#
#   Copyright © 2026 Naomi Hidalgo Piñar
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

from api import admin_router
from api.schemas.admin.system_logo import SystemLogoResponse, SystemLogoUpdateData
from api.schemas.common import ErrorResponse
from api.services.admin.system_logo import AdminSystemLogoService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse, Response

tag = "admin-system-logo"


@admin_router.get(
    "/admin/item/logo",
    tags=[tag],
    response_model=SystemLogoResponse,
    summary="Get system logo status",
    description="Returns whether a custom system-wide logo and/or collapsed "
    "logo are currently configured.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_system_logo_get(request: Request):
    try:
        status = await asyncio.to_thread(AdminSystemLogoService.get_status)
        return JSONResponse(
            content=SystemLogoResponse(**status).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get system logo status",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/item/logo",
    tags=[tag],
    status_code=204,
    response_class=Response,
    summary="Update system logo",
    description="Uploads, replaces or removes the system-wide default logo "
    "and/or collapsed logo. Logo data should be a base64 data URL.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_system_logo_put(request: Request, data: SystemLogoUpdateData):
    try:
        await asyncio.to_thread(
            AdminSystemLogoService.update, data.model_dump(exclude_none=True)
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update system logo",
            traceback.format_exc(),
        )
