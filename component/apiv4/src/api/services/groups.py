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

import re

from api.services.error import Error
from isardvdi_common.lib.users.groups.groups import GroupsProcessed

from ..schemas.allowed import AvailableUser

_REGISTER_CODE = re.compile(r"[0-9a-z]{6}")


class GroupsService:
    """
    Groups service for managing user groups.
    """

    @staticmethod
    def code_search(code: str, category_id: str) -> dict:
        if not _REGISTER_CODE.fullmatch(code):
            raise Error(
                "bad_request",
                "Invalid register code.",
                description_code="bad_request",
            )

        return GroupsProcessed.code_search(code, category_id)

    @staticmethod
    def get_users_in_group(
        group_id: str,
        roles: list[str] | None = None,
        include_secondary: bool = False,
    ) -> list[AvailableUser]:
        return GroupsProcessed.get_users_in_group(group_id, roles, include_secondary)
