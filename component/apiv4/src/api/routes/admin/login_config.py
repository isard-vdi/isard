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

from api import admin_router, manager_router
from api.schemas.admin_login_config import (
    LoginNotificationEnableRequest,
    LoginNotificationUpdateRequest,
)
from api.schemas.common import EmptyResponse, ErrorResponse
from api.services.admin_categories import AdminCategoryService
from api.services.admin_login_config import AdminLoginConfigService
from api.services.error import Error
from fastapi import Path, Request
from fastapi.responses import JSONResponse

tag = "admin-login-config"


# ══════════════════════════════════════════════════════════════════════════
#  Read login config (raw, for admin editing)
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/admin/login-config",
    tags=[tag],
    summary="Get global login config (raw)",
    description=(
        "Admin-only raw read of the global login configuration. Returns "
        "the unmerged ``Configuration.login`` payload so the admin "
        "edit-modal can show the current state. The public "
        "``GET /item/login-config`` returns the same content but goes "
        "through the same typed response model."
    ),
    responses={500: {"model": ErrorResponse}},
)
async def admin_login_config_get(request: Request):
    try:
        result = AdminCategoryService.admin_get_login_config()
        return result
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve admin login config",
            traceback.format_exc(),
        )


@manager_router.get(
    "/admin/login-config/{category_id}",
    tags=[tag],
    summary="Get per-category login config (raw)",
    description=(
        "Admin-only raw read of a single category's login notification "
        "configuration. Unmerged — used by the webapp admin "
        '"Edit category login notification" modal. The public '
        "``GET /item/login-config/{category_id}`` returns the merged "
        "global + category arrays for the login page."
    ),
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_login_config_by_category(
    request: Request,
    category_id: str = Path(..., description="Category ID"),
):
    try:
        result = AdminCategoryService.admin_get_login_config(category_id)
        return result
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve admin login config for category '{category_id}'",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Login Notification
# ══════════════════════════════════════════════════════════════════════════


@admin_router.put(
    "/login_config/notification",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Update login notification",
    description="Updates the login notification configuration for cover and form.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_login_notification_update(
    request: Request, data: LoginNotificationUpdateRequest
):
    try:
        dump = data.model_dump()
        from isardvdi_common.helpers.url_validation import validate_url_scheme

        for key in ("cover", "form"):
            if isinstance(dump.get(key), dict):
                button_url = (dump[key].get("button") or {}).get("url")
                if button_url:
                    try:
                        validate_url_scheme(button_url)
                    except ValueError as e:
                        # validate_url_scheme is framework-agnostic so it
                        # raises plain ValueError. Convert to a typed 400
                        # so admins see "bad URL" instead of generic 500.
                        raise Error("bad_request", str(e))
        AdminLoginConfigService.update_login_notification(dump)
        return {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update login notification",
            traceback.format_exc(),
        )


@admin_router.put(
    "/login_config/notification/cover/enable",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Enable/disable cover login notification",
    description="Enables or disables the login notification for the cover.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_login_notification_cover_enable(
    request: Request, data: LoginNotificationEnableRequest
):
    try:
        AdminLoginConfigService.enable_login_notification("cover", data.enabled)
        return {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to enable/disable cover login notification",
            traceback.format_exc(),
        )


@admin_router.put(
    "/login_config/notification/form/enable",
    tags=[tag],
    response_model=EmptyResponse,
    summary="Enable/disable form login notification",
    description="Enables or disables the login notification for the form.",
    responses={
        400: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def admin_login_notification_form_enable(
    request: Request, data: LoginNotificationEnableRequest
):
    try:
        AdminLoginConfigService.enable_login_notification("form", data.enabled)
        return {}
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to enable/disable form login notification",
            traceback.format_exc(),
        )
