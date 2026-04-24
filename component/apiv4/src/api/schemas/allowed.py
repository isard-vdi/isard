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


from typing import Literal, Optional, Union

from pydantic import BaseModel, Field, field_serializer


class AllowedUpdate(BaseModel):
    groups: Union[bool, list] = Field(
        default=None,
        description="List of allowed groups. If None, the field is not updated.",
    )
    users: Union[bool, list] = Field(
        default=None,
        description="List of allowed users. If None, the field is not updated.",
    )


class ItemAllowed(BaseModel):
    all: bool
    available: list[dict]


class SelectedAllowed(BaseModel):
    groups: bool | list[str]
    users: bool | list[str]


class AvailableUser(BaseModel):
    id: str = Field(description="User ID")
    name: str = Field(description="User full name")
    username: str = Field(description="User username")
    photo: Optional[str] = Field(default="", description="User photo URL")


class AvailableGroup(BaseModel):
    id: str = Field(description="Group ID")
    name: str = Field(description="Group name")


class AllowedResponse(BaseModel):
    selected: SelectedAllowed
    available_groups: bool | list[AvailableGroup] = Field(
        description="List of groups that the user is allowed to access and share items with"
    )


class AllowedBase(BaseModel):
    groups: Union[bool, list] = Field(
        default=False,
        description="List of allowed groups. If False, no groups are allowed.",
    )
    users: Union[bool, list] = Field(
        default=False,
        description="List of allowed users. If False, no users are allowed.",
    )

    @field_serializer("users", "groups")
    @classmethod
    def deduplicate_value(cls, value: Union[bool, list]) -> Union[bool, list]:
        if isinstance(value, list):
            return list(set(value))
        return value


class Allowed(AllowedBase):
    categories: Union[bool, list] = Field(
        default=False,
        description="List of allowed categories. If False, no categories are allowed.",
    )
    roles: Union[bool, list] = Field(
        default=False,
        description="List of allowed roles. If False, no roles are allowed.",
    )

    @field_serializer("categories", "roles")
    @classmethod
    def deduplicate_value(cls, value: Union[bool, list]) -> Union[bool, list]:
        if isinstance(value, list):
            return list(set(value))
        return value


# class AllowedResponse(BaseModel):

#     class AllowedCategoriesResponse(BaseModel):
#         id: str
#         name: str
#         uid: str

#     class AllowedGroupsResponse(BaseModel):
#         category_name: str
#         id: str
#         name: str
#         parent_category: str
#         uid: str

#     class AllowedRolesResponse(BaseModel):
#         id: str
#         name: str

#     class AllowedUsersResponse(BaseModel):
#         category_name: str
#         group_name: str
#         id: str
#         name: str
#         uid: str

#     categories: list[AllowedCategoriesResponse] | Literal[False]
#     groups: list[AllowedGroupsResponse] | Literal[False]
#     roles: list[AllowedRolesResponse] | Literal[False]
#     users: list[AllowedUsersResponse] | Literal[False]
