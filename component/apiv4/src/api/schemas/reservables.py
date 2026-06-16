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

from datetime import datetime, timezone
from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


def _ensure_aware_utc(value: datetime) -> datetime:
    """Coerce naive datetimes to UTC.

    Old-frontend's date pickers occasionally serialise without a
    timezone suffix; the downstream
    ``ReservablesPlannerProccess.ceil_dt`` arithmetic
    (``datetime.min.replace(tzinfo=pytz.UTC) - dt``) raises
    ``TypeError`` when ``dt`` is naive. Snap any naive value to UTC at
    the schema boundary so the planner stays naive-free.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class ReservablesListResponse(BaseModel):
    """Response model for reservables list"""

    reservables: List[str]


class ReservablePlans(BaseModel):
    """Model for booking plans data"""

    current: int
    active: bool
    profile: Optional[str] = None


class ReservableItemResponse(BaseModel):
    """Response model for individual reservable item details"""

    id: str
    name: str
    description: str
    brand: str
    model: str
    memory: str
    architecture: str
    active_profile: Optional[str] = None
    changing_to_profile: Optional[str] = None
    physical_device: Optional[str] = None
    # GPUs only: the category a card is delegated to (None = admin-only/global) and
    # its resolved name. Computed by the _common listing query; declared here so
    # FastAPI does not strip them from the response (otherwise the webapp/old-frontend
    # delegated-category label never renders).
    category: Optional[str] = None
    category_name: Optional[str] = None
    # GPUs only: the auto per-card passthrough identity used as the default variant
    # suggestion in the admin Variant column; declared so FastAPI keeps it.
    passthrough_variant: Optional[str] = None
    profiles_enabled: List[str]
    plans: ReservablePlans
    desktops_started: List[str] = []
    available_units: int = 0
    gpu_warnings: List[str] = []


class ReservableDetailResponse(BaseModel):
    """Response model for reservable detail list"""

    items: List[ReservableItemResponse]


class AvailableReservable(BaseModel):
    """Available reservable item"""

    id: str
    name: str
    description: str
    max_booking_date: str


class AvailableReservablesResponse(BaseModel):
    """Response model for available reservables"""

    reservables_available: Optional[list[AvailableReservable]]


class ReservableSubitemResponse(BaseModel):
    """Response model for a single reservable subitem (e.g., a vGPU
    profile in the catalog of a GPU model)."""

    id: str
    name: str
    description: str
    profile: str
    memory: int
    units: int


class ReservableProfileResponse(BaseModel):
    """Response model for reservable profiles"""

    id: str
    brand: str
    model: str
    description: str
    memory: str
    architecture: str
    profiles: List[dict]


class AddReservableItemRequest(BaseModel):
    """Request model for adding a new reservable item"""

    name: str
    bookable: str
    description: Optional[str] = ""


class UpdateReservableItemRequest(BaseModel):
    """Request model for updating a reservable item's name and description,
    and/or delegating it to a category (upstream MR !4546): an empty string
    clears the delegation (back to admin-only/global)."""

    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=64)


class EnableReservableRequest(BaseModel):
    """Request model for enabling/disabling a reservable subitem"""

    enabled: bool


class CheckLastResponse(BaseModel):
    """Response model for check last subitem/item"""

    last: List[bool]
    desktops: List[dict]
    plans: List[dict]
    bookings: List[dict]
    deployments: List[dict]


class PlannerPlanResponse(BaseModel):
    """Response model for a resource planner plan"""

    id: str
    item_type: str
    item_id: str
    subitem_id: str
    units: int
    start: str
    end: str
    user_id: str
    event_type: str
    item: Optional[str] = None
    bookings: Optional[int] = None


class CreatePlanRequest(BaseModel):
    """Request model for creating a plan"""

    item_type: str
    item_id: str
    subitem_id: str
    start: datetime
    end: datetime

    _coerce_start = field_validator("start")(lambda cls, v: _ensure_aware_utc(v))
    _coerce_end = field_validator("end")(lambda cls, v: _ensure_aware_utc(v))


class UpdatePlanRequest(BaseModel):
    """Request model for updating a plan"""

    start: datetime
    end: datetime

    _coerce_start = field_validator("start")(lambda cls, v: _ensure_aware_utc(v))
    _coerce_end = field_validator("end")(lambda cls, v: _ensure_aware_utc(v))


class BookingProvisioningRequest(BaseModel):
    """Request model for booking provisioning"""

    subitems: dict
    units: int
    priority: dict
    block_interval: int
