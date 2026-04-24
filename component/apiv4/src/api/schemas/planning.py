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

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class CreatePlanningRequest(BaseModel):
    """Request model for creating a planning"""

    item_type: str = Field(
        ..., description="Type of the reservable item (e.g., 'gpus')"
    )
    item_id: str = Field(
        ...,
        description="ID of the reservable item (e.g vGPU ID)",
    )
    subitem_id: str = Field(
        ...,
        description="ID of the subitem within the reservable item (e.g vGPU profile ID)",
    )
    start: datetime = Field(
        ...,
        description="Start datetime for the planning",
    )
    end: datetime = Field(
        ...,
        description="End datetime for the planning",
    )


class PlanningItem(BaseModel):
    """Model for a planning item"""

    id: str
    item_id: str
    subitem_id: str
    start: datetime
    end: datetime
    item_type: Optional[str] = None
    units: Optional[int] = None
    priority: Optional[int] = None


class PlanningListResponse(BaseModel):
    """Response model for listing plannings"""

    plannings: List[PlanningItem]


class PlanningDeleteResponse(BaseModel):
    """Response model for deleting a planning"""

    deleted: bool
    plan_id: str


class ReservablePlans(BaseModel):
    """Model for booking plans data"""

    current: int
    active: bool
    profile: Optional[str] = None
