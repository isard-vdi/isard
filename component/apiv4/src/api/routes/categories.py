#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Miriam Melina Gamboa Valdez
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import asyncio
import traceback
from typing import List, Optional

from api import advanced_router
from api.dependencies.alloweds import owns_domain_id
from api.schemas.categories import (
    CategoriesUsersSearchResponse,
    GroupsInCategoryResponse,
)
from api.schemas.common import ErrorResponse
from api.services.categories import CategoryService
from api.services.error import Error
from fastapi import Depends, Path, Query, Request
from fastapi.responses import JSONResponse

tag = "categories"


@advanced_router.get(
    # NOTE: path has 4 segments after /api/v4 (item/category/users/search) so
    # it cannot collide with the 3-segment /item/category/{custom_url} catch-all
    # declared earlier on open_router (see login.py).
    "/item/category/users/search",
    response_model=CategoriesUsersSearchResponse,
    tags=[tag],
    summary="Get users in the user category",
    description="Returns a list of users in a specific category.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def search_users_in_category(
    request: Request,
    search: str = Query(..., description="String to search for users"),
    limit: int = Query(
        50, ge=1, le=200, description="Maximum number of users to return."
    ),
    roles: Optional[List[str]] = Query(
        None,
        description="Restrict results to these roles",
    ),
):
    try:
        return JSONResponse(
            content=CategoriesUsersSearchResponse(
                **await asyncio.to_thread(
                    CategoryService.search_users_in_category,
                    request.token_payload["category_id"],
                    search,
                    limit,
                    roles,
                )
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            "Failed to search users in category",
            traceback.format_exc(),
        )


@advanced_router.get(
    "/item/category/allowed/get-available-groups",
    response_model=GroupsInCategoryResponse,
    tags=[tag],
    summary="Get available groups for a category",
    description="Returns a list of available groups for a specific category.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_available_groups_for_category(
    request: Request,
):
    try:
        return JSONResponse(
            content=GroupsInCategoryResponse(
                available_groups=CategoryService.get_available_groups_in_category(
                    request.token_payload["category_id"]
                )
            ).model_dump(mode="json"),
            status_code=200,
        )
    except Error as e:
        raise e
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve available groups for category {request.token_payload['category_id']}",
            traceback.format_exc(),
        )
