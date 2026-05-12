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
from typing import Union

from api import admin_router, manager_router
from api.schemas.admin.tables import TableItem, TableListRequest
from api.schemas.common import EmptyResponse, ErrorResponse
from api.services.admin.tables import AdminTablesService
from api.services.error import Error
from fastapi import Path, Request
from fastapi.responses import JSONResponse, Response

tag = "admin_tables"


@manager_router.get(
    "/admin/table/{table}",
    tags=[tag],
    response_model=Union[TableItem, list[TableItem]],
    summary="Get items from a table",
    description="Get a single item by ID or list all items from a table. "
    "Admins see all items; managers are scoped to their category.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_table_get(
    request: Request,
    table: str = Path(..., description="Database table name"),
):
    try:
        options = dict(request.query_params)
        result = await asyncio.to_thread(
            AdminTablesService.get_table, table, request.token_payload, options
        )
        if isinstance(result, list):
            return JSONResponse(
                content=[TableItem(**row).model_dump(mode="json") for row in result],
                status_code=200,
            )
        return JSONResponse(
            content=TableItem(**(result or {})).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get table items",
            traceback.format_exc(),
        )


@manager_router.post(
    "/admin/table/{table}",
    tags=[tag],
    response_model=Union[TableItem, list[TableItem]],
    summary="List table items with filters",
    description="List items from a table with optional filters, pluck, order, and index. "
    "Admins see all items; managers are scoped to their category.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_table_list(
    request: Request,
    data: TableListRequest,
    table: str = Path(..., description="Database table name"),
):
    try:
        options = data.model_dump(exclude_none=True)
        result = await asyncio.to_thread(
            AdminTablesService.get_table, table, request.token_payload, options
        )
        if isinstance(result, list):
            return JSONResponse(
                content=[TableItem(**row).model_dump(mode="json") for row in result],
                status_code=200,
            )
        return JSONResponse(
            content=TableItem(**(result or {})).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list table items",
            traceback.format_exc(),
        )


@admin_router.post(
    "/admin/table/add/{table}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Insert a new item into a table",
    description="Insert a new item into the specified table. "
    "Checks for duplicate names in tables that require it.",
    responses={
        403: {"model": ErrorResponse},
        409: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_table_insert(
    request: Request,
    data: dict,
    table: str = Path(..., description="Database table name"),
):
    try:
        await asyncio.to_thread(AdminTablesService.insert_table_item, table, data)
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to insert table item",
            traceback.format_exc(),
        )


@admin_router.put(
    "/admin/table/update/{table}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update an item in a table",
    description="Update an existing item in the specified table. "
    "Checks for duplicate names in tables that require it.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_table_update(
    request: Request,
    data: dict,
    table: str = Path(..., description="Database table name"),
):
    try:
        await asyncio.to_thread(AdminTablesService.update_table_item, table, data)
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update table item",
            traceback.format_exc(),
        )


@admin_router.delete(
    "/admin/table/{table}/{item_id}",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Delete an item from a table",
    description="Delete an item from the specified table by ID. "
    "Unassigns resources from desktops and deployments for relevant tables.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_table_delete(
    request: Request,
    table: str = Path(..., description="Database table name"),
    item_id: str = Path(..., description="Item ID to delete"),
):
    try:
        await asyncio.to_thread(AdminTablesService.delete_table_item, table, item_id)
        return Response(status_code=204)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to delete table item",
            traceback.format_exc(),
        )
