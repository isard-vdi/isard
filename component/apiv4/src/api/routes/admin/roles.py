#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import traceback

from api import admin_router
from api.schemas.common import ErrorResponse
from api.services.admin_roles import AdminRolesService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse

tag = "admin_roles"


# =============================================================================
# ROLES ENDPOINTS (admin_router)
# =============================================================================


@admin_router.get(
    "/admin/roles",
    tags=[tag],
    summary="List all roles",
    description="Returns all available user roles.",
    responses={500: {"model": ErrorResponse}},
)
async def admin_list_roles(request: Request):
    try:
        roles = AdminRolesService.get_roles()
        return JSONResponse(content=roles, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to list roles",
            traceback.format_exc(),
        )


@admin_router.get(
    "/admin/role/{role_id}",
    tags=[tag],
    summary="Get a role",
    description="Returns a role by its ID.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_get_role(request: Request, role_id: str):
    try:
        role = AdminRolesService.get_role(role_id)
        return JSONResponse(content=role, status_code=200)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get role",
            traceback.format_exc(),
        )
