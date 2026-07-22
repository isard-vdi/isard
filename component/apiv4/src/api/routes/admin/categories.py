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
from typing import Literal

from api import manager_router
from api.schemas.admin.categories import (
    BrandingResponse,
    BrandingUpdateData,
    CategoryAuthenticationResponse,
    CategoryLoginNotificationData,
    CategoryLoginNotificationEnableData,
)
from api.schemas.admin.users import AdminCategoryAuthenticationData
from api.schemas.common import ErrorResponse
from api.services.admin.categories import AdminCategoryService
from api.services.error import Error
from fastapi import Request
from fastapi.responses import JSONResponse, Response

tag = "admin-categories"


# ══════════════════════════════════════════════════════════════════════════
#  Branding
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/admin/item/category/{category_id}/branding",
    tags=[tag],
    response_model=BrandingResponse,
    summary="Get category branding",
    description="Returns branding configuration (domain + logo) for a category.",
    responses={
        200: {"description": "Branding configuration"},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_category_branding(request: Request, category_id: str):
    try:
        branding = await asyncio.to_thread(
            AdminCategoryService.get_branding, request.token_payload, category_id
        )
        return JSONResponse(
            content=BrandingResponse(**(branding or {})).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve category branding",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/item/category/{category_id}/branding",
    tags=[tag],
    status_code=204,
    response_class=Response,
    summary="Update category branding",
    description="Updates branding configuration (domain + logo) for a category. "
    "Logo data should be a base64 data URL.",
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_category_branding(
    request: Request, category_id: str, data: BrandingUpdateData
):
    try:
        await asyncio.to_thread(
            AdminCategoryService.update_branding,
            request.token_payload,
            category_id,
            data.model_dump(exclude_none=True),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update category branding",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Authentication
# ══════════════════════════════════════════════════════════════════════════


@manager_router.get(
    "/admin/item/category/{category_id}/authentication",
    tags=[tag],
    response_model=CategoryAuthenticationResponse,
    summary="Get category authentication",
    description="Returns authentication provider configuration for a category "
    "with sensitive fields stripped.",
    responses={
        200: {"description": "Authentication configuration"},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_category_authentication(request: Request, category_id: str):
    try:
        auth = await asyncio.to_thread(
            AdminCategoryService.get_authentication, request.token_payload, category_id
        )
        return JSONResponse(
            content=CategoryAuthenticationResponse(**(auth or {})).model_dump(
                mode="json"
            ),
            status_code=200,
        )
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve category authentication",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/item/category/{category_id}/authentication",
    tags=[tag],
    status_code=204,
    response_class=Response,
    summary="Update category authentication",
    description="Updates authentication provider configuration for a category. "
    "Sensitive fields (password, client_secret) are preserved if left empty in "
    "the payload.",
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_category_authentication(
    request: Request, category_id: str, data: AdminCategoryAuthenticationData
):
    try:
        await asyncio.to_thread(
            AdminCategoryService.update_authentication,
            request.token_payload,
            category_id,
            data.model_dump(),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update category authentication",
            traceback.format_exc(),
        )


# ══════════════════════════════════════════════════════════════════════════
#  Per-category Login Notification
# ══════════════════════════════════════════════════════════════════════════


@manager_router.put(
    "/admin/item/category/{category_id}/login_notification",
    tags=[tag],
    status_code=204,
    response_class=Response,
    summary="Update category login notification",
    description="Updates login notification configuration for a specific category.",
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def update_category_login_notification(
    request: Request, category_id: str, data: CategoryLoginNotificationData
):
    try:
        await asyncio.to_thread(
            AdminCategoryService.update_login_notification,
            request.token_payload,
            category_id,
            data.model_dump(exclude_none=True),
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to update category login notification",
            traceback.format_exc(),
        )


@manager_router.put(
    "/admin/item/category/{category_id}/login_notification/{notification_type}/enable",
    tags=[tag],
    status_code=204,
    response_class=Response,
    summary="Enable/disable category login notification",
    description="Enables or disables a specific login notification type for a category.",
    responses={
        400: {"model": ErrorResponse},
        403: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def enable_category_login_notification(
    request: Request,
    category_id: str,
    notification_type: Literal["cover", "form"],
    data: CategoryLoginNotificationEnableData,
):
    try:
        await asyncio.to_thread(
            AdminCategoryService.enable_login_notification,
            request.token_payload,
            category_id,
            notification_type,
            data.enabled,
        )
        return Response(status_code=204)
    except Error:
        raise
    except Exception:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to enable/disable category login notification",
            traceback.format_exc(),
        )
