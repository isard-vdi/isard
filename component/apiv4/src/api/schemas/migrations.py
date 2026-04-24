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

from typing import Literal, Optional

from isardvdi_common.schemas.domains import DomainKindEnum
from pydantic import BaseModel, Field


class MigrationExportResponse(BaseModel):
    """
    Response model for exporting user data for migration.
    """

    token: str = Field(
        ..., description="JWT token containing the user's data for migration."
    )


class ImportUserRequest(BaseModel):
    """
    Request model for importing user data for migration.
    """

    token: str = Field(
        ..., description="JWT token containing the user's data for migration."
    )


class MigrationProviderEnabledResponse(BaseModel):
    """
    Response model for provider migration export/import enabled status.
    """

    enabled: bool = Field(
        ..., description="Whether the provider allows export or import migrations."
    )


class MigrationListDesktop(BaseModel):
    id: str = Field(..., description="Item ID")
    name: str = Field(..., description="Item name")
    kind: Literal[DomainKindEnum.desktop.value] = Field(
        ..., description="Type of item."
    )
    user: str = Field(..., description="User ID who owns the item")
    username: str = Field(..., description="Username of the owner")
    user_name: str = Field(..., description="Display name of the user")
    persistent: bool = Field(..., description="Whether the item is persistent")


class MigrationListTemplate(BaseModel):
    id: str = Field(..., description="Item ID")
    name: str = Field(..., description="Item name")
    kind: Literal[DomainKindEnum.template.value] = Field(
        ..., description="Type of item."
    )
    user: str = Field(..., description="User ID who owns the item")
    category: str = Field(..., description="Category ID")
    group: str = Field(..., description="Group ID")
    username: str = Field(..., description="Username of the owner")
    user_name: str = Field(..., description="Display name of the user")
    duplicate_parent_template: Optional[str] = Field(
        None, description="Parent template ID if duplicated"
    )


class MigrationListMedia(BaseModel):
    id: str = Field(..., description="Item ID")
    name: str = Field(..., description="Item name")
    user: str = Field(..., description="User ID who owns the item")
    username: str = Field(..., description="Username of the owner")
    user_name: str = Field(..., description="Display name of the user")


class MigrationListDeployment(BaseModel):
    id: str = Field(..., description="Item ID")
    name: str = Field(..., description="Item name")
    user: str = Field(..., description="User ID who owns the item")
    username: str = Field(..., description="Username of the owner")
    user_name: str = Field(..., description="Display name of the user")


class MigrationListItemsResponse(BaseModel):
    """
    Response model for listing items available for migration.
    """

    desktops: list[MigrationListDesktop] = Field(
        ..., description="Desktops available for migration."
    )
    templates: list[MigrationListTemplate] = Field(
        ..., description="Templates available for migration."
    )
    media: list[MigrationListMedia] = Field(
        ..., description="Media available for migration."
    )
    deployments: list[MigrationListDeployment] = Field(
        ..., description="Deployments available for migration."
    )
    action_after_migrate: Literal["none", "disable", "delete"] = Field(
        ...,
        description="Action that will be performed on the user account after migration.",
    )


class MigrationConfigResponse(BaseModel):
    """Response model for migration configuration."""

    check_quotas: bool = Field(
        default=False,
        description="Whether quota checks are enforced during migration.",
    )


class MigrationConfigUpdateRequest(BaseModel):
    """Request model for updating migration configuration."""

    check_quotas: Optional[bool] = Field(
        default=None,
        description="Whether quota checks should be enforced during migration.",
    )


class AdminMigrationEntry(BaseModel):
    """A single migration entry for admin listing."""

    id: str
    origin_user: str
    target_user: Optional[str] = None
    status: str
    token: str


class AdminMigrationsResponse(BaseModel):
    """Response for admin migrations listing."""

    migrations: list[dict]
