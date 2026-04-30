#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import traceback

from api import admin_router
from api.schemas.common import ErrorResponse
from api.services.admin.roles import AdminRolesService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse

tag = "admin_roles"


# =============================================================================
# ROLES ENDPOINTS (admin_router)
# =============================================================================
#
# ``GET /admin/roles`` lives on manager_router in admin/users.py and
# is registered first, so any handler defined here would be dead code.
# Only the per-role lookup belongs here.


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
        return role
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to get role",
            traceback.format_exc(),
        )
