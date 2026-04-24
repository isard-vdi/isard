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

from api import token_router
from api.schemas.admin_tables import (
    AllowedGetRequest,
    AllowedTermRequest,
    AllowedUpdateRequest,
)
from api.schemas.common import EmptyResponse, ErrorResponse
from api.services.admin_alloweds import AdminAllowedsService
from api.services.error import Error
from fastapi import Path, Request
from fastapi.responses import JSONResponse

tag = "admin_alloweds"


@token_router.post(
    "/admin/allowed/term/{table}",
    tags=[tag],
    summary="Search table items by term",
    description="Search for items in a table matching a term. "
    "Returns roles, categories, groups, and users matching a 2+ character term. "
    "Results are filtered based on the user's role and category.",
    responses={
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def alloweds_table_term(
    request: Request,
    data: AllowedTermRequest,
    table: str = Path(..., description="Table to search in"),
):
    try:
        result = AdminAllowedsService.get_table_term(
            table, data.model_dump(exclude_none=True), request.token_payload
        )
        return JSONResponse(content=result, status_code=200)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to search table term",
            traceback.format_exc(),
        )


@token_router.post(
    "/admin/allowed/update/{table}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update allowed access for a table item",
    description="Update the allowed access permissions (roles, categories, groups, users) "
    "for an item in the specified table. Handles special bastion table cases.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_allowed_update(
    request: Request,
    data: AllowedUpdateRequest,
    table: str = Path(..., description="Table containing the item"),
):
    try:
        AdminAllowedsService.update_allowed(
            table, data.model_dump(), request.token_payload
        )
        return JSONResponse(
            content=EmptyResponse().model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update allowed access",
            traceback.format_exc(),
        )


@token_router.post(
    "/allowed/table/{table}",
    tags=[tag],
    summary="Get allowed access list for a table item",
    description="Get the allowed access configuration for an item, "
    "enriched with names for roles, categories, groups, and users.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def allowed_table(
    request: Request,
    data: AllowedGetRequest,
    table: str = Path(..., description="Table containing the item"),
):
    try:
        result = AdminAllowedsService.get_allowed_table(table, data.model_dump())
        return JSONResponse(content=result, status_code=200)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get allowed access list",
            traceback.format_exc(),
        )
