#
#   Copyright © 2025 Naomi Hidalgo Piñar
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

from api import disclaimer_router, open_router
from api.schemas.common import ErrorResponse, SimpleResponse
from api.schemas.login import (
    CategoryResponse,
    CategoryResponseList,
    DisclaimerResponse,
    LoginConfigResponse,
)
from api.services.categories import CategoryService
from api.services.config import ConfigService
from api.services.error import Error
from api.services.notifications_templates import NotificationsTemplatesService
from fastapi import Request
from fastapi.responses import JSONResponse


@open_router.get(
    "/items/categories",
    tags=["categories"],
    response_model=CategoryResponseList,
    summary="Get all categories",
    description="Returns a list of all available categories.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def api_v4_categories(request: Request):
    try:
        domain = request.headers.get("host")
        categories = CategoryService.get_categories_frontend(domain=domain)
        return CategoryResponseList(categories=categories)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve categories",
            traceback.format_exc(),
        )


@open_router.get(
    "/item/category/{custom_url}",
    tags=["categories"],
    response_model=CategoryResponse,
    summary="Get category details",
    description="Returns detailed information about a specific category.",
    responses={
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def api_v4_category(custom_url: str, request: Request):
    try:
        domain = request.headers.get("host")
        category = CategoryService.get_category_by_custom_url(custom_url, domain=domain)
        return CategoryResponse(**category)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve category with custom URL '{custom_url}'",
            traceback.format_exc(),
        )


@open_router.get(
    "/item/login-config",
    tags=["login"],
    response_model=LoginConfigResponse,
    summary="Get login configuration",
    description="Returns login page configuration including notifications.",
    responses={
        500: {"model": ErrorResponse},
    },
)
async def api_v4_login_config(request: Request):
    try:
        config = ConfigService.get_login_config()
        return LoginConfigResponse(**config)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve login configuration",
            traceback.format_exc(),
        )


@disclaimer_router.get(
    "/item/disclaimer",
    tags=["disclaimer"],
    response_model=DisclaimerResponse,
    summary="Get disclaimer content",
    description="Returns disclaimer content for the login page.",
)
async def api_v4_disclaimer(request: Request):
    try:
        disclaimer = NotificationsTemplatesService.get_disclaimer(
            user_id=request.token_payload["user_id"]
        )
        return DisclaimerResponse(**disclaimer)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to retrieve user disclaimer",
            traceback.format_exc(),
        )
