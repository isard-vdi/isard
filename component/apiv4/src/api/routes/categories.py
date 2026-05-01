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
from api.schemas.categories import CategoriesUsersSearchResponse
from api.schemas.common import ErrorResponse
from api.services.categories import CategoryService
from api.services.error import Error
from cachetools import TTLCache, cached
from fastapi import Depends, Path, Query, Request
from fastapi.responses import JSONResponse

tag = "categories"

# Named cache so writers can invalidate it (and tests can clear between
# cases). Search results are stable for ~10 s.
category_users_search_cache: TTLCache = TTLCache(maxsize=20, ttl=10)


def clear_category_users_search_cache() -> None:
    """Invalidate the category user-search cache after user-list mutations."""
    category_users_search_cache.clear()


@cached(cache=category_users_search_cache)
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
):
    try:
        return CategoriesUsersSearchResponse(
            users=await asyncio.to_thread(
                CategoryService.search_users_in_category,
                request.token_payload["category_id"],
                search,
            )
        )
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve group users",
            traceback.format_exc(),
        )
