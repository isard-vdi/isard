#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Naomi Hidalgo Piñar
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


from typing import Optional, Union

from pydantic import BaseModel, Field


class Allowed(BaseModel):
    categories: Union[bool, list] = False
    groups: Union[bool, list] = False
    roles: Union[bool, list] = False
    users: Union[bool, list] = False


class AllowedUpdate(BaseModel):
    """Schema for partial updates of allowed permissions."""

    categories: Optional[Union[bool, list]] = Field(
        default=None,
        description="List of allowed categories. If False, no categories are allowed. If None, field is not updated.",
    )
    groups: Optional[Union[bool, list]] = Field(
        default=None,
        description="List of allowed groups. If False, no groups are allowed. If None, field is not updated.",
    )
    roles: Optional[Union[bool, list]] = Field(
        default=None,
        description="List of allowed roles. If False, no roles are allowed. If None, field is not updated.",
    )
    users: Optional[Union[bool, list]] = Field(
        default=None,
        description="List of allowed users. If False, no users are allowed. If None, field is not updated.",
    )
