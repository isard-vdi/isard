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
from uuid import uuid4

from isardvdi_common.models.deployment import Deployment as RethinkDeployment
from isardvdi_common.models.domain import Domain as RethinkDomain
from isardvdi_common.models.user import User as RethinkUser
from pydantic import BaseModel, Field


class MaintenanceStatusResponse(BaseModel):
    """Maintenance status response model"""

    enabled: bool = Field(
        default=False,
        description="Indicates whether the maintenance mode is enabled or not.",
    )


class MaintenanceTextResponse(BaseModel):

    enabled: bool = Field(
        default=True,
        description="Indicates whether the custom maintenance text is set or not.",
    )
    title: str | None = Field(
        default=None,
        description="Title to display during maintenance mode.",
    )
    body: str | None = Field(
        default=None,
        description="Description to display during maintenance mode.",
    )


class MaintenanceStatusUpdate(BaseModel):
    """Maintenance status update model"""

    enabled: bool = Field(
        default=False,
        description="Indicates whether the maintenance mode is enabled or not.",
    )


class MaintenanceTextGetResponse(BaseModel):
    """Response model for GET maintenance text (admin)"""

    text: dict


class MaintenanceTextUpdate(BaseModel):
    """Maintenance text update model"""

    title: Optional[str] = Field(
        default=None,
        description="Title to display during maintenance mode. If not provided, the existing title will be used.",
    )
    body: Optional[str] = Field(
        default=None,
        description="Text to display during maintenance mode. If not provided, the existing text will be used.",
    )
