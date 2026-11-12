#
#   Copyright © 2026 Adrià Garriga Bassas
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
from api.schemas.admin.frontend_mode_rules import (
    FrontendModeRulesCreateRequest,
    FrontendModeRulesResponse,
)
from api.schemas.common import ErrorResponse
from api.services.admin.frontend_mode_rules import AdminFrontendModeRulesService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse, Response

tag = "admin_frontend_mode_rules"


@admin_router.get(
    "/items/frontend-mode-rules",
    tags=[tag],
    response_model=FrontendModeRulesResponse,
    summary="Get all frontend mode rules",
    description="Returns all frontend mode rules ordered by priority.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def get_all_frontend_mode_rules(request: Request):
    try:
        rules = await asyncio.to_thread(
            AdminFrontendModeRulesService.get_all_frontend_mode_rules
        )
        return JSONResponse(
            content=FrontendModeRulesResponse(rules=rules).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve admin frontend mode rules",
            traceback.format_exc(),
        )


@admin_router.post(
    "/item/frontend-mode-rule",
    tags=[tag],
    status_code=204,
    response_class=Response,
    summary="Create a new frontend mode rule",
    description="Creates a new frontend mode rule.",
    responses={
        204: {"description": "Frontend mode rule created successfully."},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def create_frontend_mode_rule(
    request: Request, data: FrontendModeRulesCreateRequest
):
    try:
        await asyncio.to_thread(
            AdminFrontendModeRulesService.create_frontend_mode_rule, data.model_dump()
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to create a new frontend mode rule",
            traceback.format_exc(),
        )
