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

import traceback

from api import advanced_router
from api.dependencies.alloweds import owns_domain_id
from api.schemas.common import ErrorResponse
from api.schemas.groups import GroupUsersResponse
from api.services.error import Error
from api.services.groups import GroupsService
from cachetools import TTLCache, cached
from fastapi import Depends, Path, Request
from fastapi.responses import JSONResponse

tag = "groups"


@cached(cache=TTLCache(maxsize=20, ttl=10))
@advanced_router.get(
    "/item/group/{group_id}/get-users",
    response_model=GroupUsersResponse,
    tags=[tag],
    summary="Get users in a group",
    description="Returns a list of users in a specific group.",
    responses={
        403: {"model": ErrorResponse},
        404: {"model": ErrorResponse},
        500: {"model": ErrorResponse},
    },
)
async def get_users_in_group(
    request: Request,
    group_id: str = Path(..., description="The ID of the group"),
    owns_group_id=Depends(owns_domain_id("group_id")),
):
    try:
        users = GroupsService.get_users_in_group(group_id)
        return GroupUsersResponse(users=users)
    except Error:
        raise
    except Exception as e:
        raise await Error.create(
            request,
            "internal_server",
            f"Failed to retrieve group users",
            traceback.format_exc(),
        )
