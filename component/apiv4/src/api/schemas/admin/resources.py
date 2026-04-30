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

from typing import Optional

from pydantic import BaseModel, Field


class QosDiskCreateRequest(BaseModel):
    """Request body for creating a QoS disk profile."""

    id: Optional[str] = Field(default=None, description="QoS disk profile ID")
    name: str = Field(description="QoS disk profile name")
    description: Optional[str] = Field(
        default=None, description="QoS disk profile description"
    )
    iotune: dict = Field(description="IO tune parameters")
    allowed: Optional[dict] = Field(
        default=None, description="Allowed access configuration"
    )


class QosDiskUpdateRequest(BaseModel):
    """Request body for updating a QoS disk profile."""

    id: str = Field(description="QoS disk profile ID")
    name: str = Field(description="QoS disk profile name")
    description: Optional[str] = Field(
        default=None, description="QoS disk profile description"
    )
    iotune: Optional[dict] = Field(default=None, description="IO tune parameters")
    allowed: Optional[dict] = Field(
        default=None, description="Allowed access configuration"
    )
