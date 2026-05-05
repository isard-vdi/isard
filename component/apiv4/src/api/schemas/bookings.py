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
from typing import Annotated, Literal, Optional

from isardvdi_common.schemas.domains import DomainKindEnum
from pydantic import (
    AliasChoices,
    AwareDatetime,
    BaseModel,
    ConfigDict,
    Field,
    RootModel,
    field_validator,
)


def _ensure_aware_utc(value: datetime) -> datetime:
    """Coerce naive datetimes to UTC at the schema boundary.

    The legacy Vue 2 frontend sometimes serialises booking dates without
    a timezone suffix (`bookingUtils.formatAsUTC` quirk). The downstream
    ``BookingsProcessed.add`` /``update`` use
    ``datetime.strptime(..., "%Y-%m-%dT%H:%M%z")`` which rejects naive
    values with a confusing ``ValueError``. Snap any naive value to UTC
    here so the service layer always sees aware datetimes.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class BookingPriorityUser(BaseModel):
    """One row of ``POST /items/bookings/priorities``."""

    model_config = {"extra": "allow"}

    id: Optional[str] = None
    username: Optional[str] = None
    name: Optional[str] = None


class CreateBookingEventRequest(BaseModel):
    """Request model for creating a booking event.

    Vue 2 (``old-frontend``) historically posts ``element_id`` /
    ``element_type`` while Vue 3 + new clients post ``item_id`` /
    ``item_type``. ``populate_by_name=True`` plus ``AliasChoices``
    accepts both wire shapes so the legacy form keeps working.
    """

    model_config = ConfigDict(populate_by_name=True)

    item_id: str = Field(
        description="ID of the reservable item (e.g., desktop ID or deployment ID)",
        validation_alias=AliasChoices("item_id", "element_id"),
    )
    item_type: Literal[DomainKindEnum.desktop.value, "deployment"] = Field(
        description="Type of the reservable item (e.g., 'desktop', 'deployment')",
        default=DomainKindEnum.desktop.value,
        validation_alias=AliasChoices("item_type", "element_type"),
    )
    start: datetime = Field(
        description="Start datetime for the booking event",
    )
    end: datetime = Field(
        description="End datetime for the booking event",
    )
    title: Optional[str] = Field(default="", description="Title of the booking event")
    now: Optional[bool] = Field(
        False,
        description="If true, the booking starts now and the start field is ignored",
    )

    @field_validator("start", "end")
    @classmethod
    def _coerce_naive_to_utc(cls, value: datetime) -> datetime:
        return _ensure_aware_utc(value)


class UpdateBookingEventRequest(BaseModel):
    """Request model for updating a booking event.

    Form payload: ``title``/``start``/``end``. ``element_type`` is
    preserved for backwards compatibility but unused on the server side.
    """

    title: str = Field(default="", description="New title for the booking")
    start: datetime = Field(description="New start datetime for the booking")
    end: datetime = Field(description="New end datetime for the booking")
    element_type: Optional[DomainKindEnum] = Field(
        default=None,
        description="Deprecated: unused on the server side.",
    )

    @field_validator("start", "end")
    @classmethod
    def _coerce_naive_to_utc(cls, value: datetime) -> datetime:
        return _ensure_aware_utc(value)


class BookingEventReservables(BaseModel):
    """Reservables associated with a booking event"""

    vgpus: list[str] = Field(
        description="List of vGPU profile IDs associated with the booking event",
        json_schema_extra={"example": ["gpu-1234-profile-1", "gpu-5678-profile-2"]},
    )


class BookingEventResponse(BaseModel):
    """Response model for booking events"""

    id: str
    item_id: str
    item_type: str
    units: int
    reservables: BookingEventReservables
    start: str
    end: str
    title: str
    user_id: str
    editable: bool


class BookingPriorityDesktopResponse(BaseModel):
    """Response model for booking priority desktop.

    The dict returned by ``Bookings.get_user_priority(...)`` (per-vgpu
    priorities + the most-restrictive ``forbid_time/max_time/max_items``)
    merged with the desktop ``name``. ``max_time`` and ``max_items`` may
    be ``None`` when no priority rule matched.
    """

    model_config = {"extra": "allow"}

    priority: dict[str, int]
    forbid_time: int
    max_time: Optional[int] = None
    max_items: Optional[int] = None
    name: str


class MaxBookingDateResponse(BaseModel):
    """Response model for max booking date"""

    max_booking_date: str


class UserBookingPlan(BaseModel):
    plan_id: Annotated[
        str,
        Field(description="The ID of the booking plan."),
    ]
    priority: Annotated[
        int,
        Field(description="The priority level of the booking plan."),
    ]
    item_id: Annotated[
        str,
        Field(description="The ID of the item associated with the booking plan."),
    ]
    subitem_id: Annotated[
        str,
        Field(description="The ID of the subitem associated with the booking plan."),
    ]
    units_booked: Annotated[
        int,
        Field(description="The number of units booked under this plan."),
    ]


class UserBookingResponse(BaseModel):
    """Response model for user bookings"""

    id: Annotated[
        str,
        Field(description="The ID of the booking event."),
    ]
    item_id: Annotated[
        str,
        Field(description="The ID of the item using the booking."),
    ]
    item_type: Annotated[
        Literal["desktop", "deployment"],
        Field(description="The type of the item using the booking."),
    ]
    units: Annotated[
        int,
        Field(description="The number of units booked."),
    ]
    reservables: Annotated[
        dict[Literal["vgpus"], list[str]],
        Field(description="The reservables associated with the booking."),
    ]
    start: Annotated[
        AwareDatetime,
        Field(description="The start time of the booking."),
    ]
    end: Annotated[
        AwareDatetime,
        Field(description="The end time of the booking."),
    ]
    title: Annotated[
        str,
        Field(description="The title of the booking."),
    ]
    user_id: Annotated[
        str,
        Field(description="The ID of the user who made the booking."),
    ]
    editable: Annotated[
        bool,
        Field(description="Whether the booking is editable by the user."),
    ]
    event_type: Annotated[
        Literal["event", "available", "unavailable", "overridable"],
        Field(
            description="Whether it's an availability event or a user booking event."
        ),
    ]
    plans: Annotated[
        list[UserBookingPlan],
        Field(description="List of booking plans."),
    ]


class AvailabilityResponse(BaseModel):
    """Response model for availability"""

    start: Annotated[
        AwareDatetime,
        Field(description="The start time of the availability period."),
    ]
    end: Annotated[
        AwareDatetime,
        Field(description="The end time of the availability period."),
    ]
    event_type: Annotated[
        Literal["available", "unavailable", "overridable"],
        Field(description="Type of availability event."),
    ]
    units: Annotated[
        Literal["Enough"] | int,
        Field(description="Number of units available"),
    ]


class ItemBookingsResponse(RootModel):
    root: list[UserBookingResponse | AvailabilityResponse]


class AdminBookingResponse(BaseModel):
    """Response model for admin bookings (includes username and category)"""

    id: str
    item_id: str
    item_type: str
    units: int
    reservables: dict
    start: AwareDatetime
    end: AwareDatetime
    title: str
    user_id: str
    plans: list[UserBookingPlan]
    username: str
    category: str


class PriorityRuleResponse(BaseModel):
    """Response model for priority rules"""

    rule_id: str


class GetUsersPrioritiesRequest(BaseModel):
    """Request model for getting users by priority rule"""

    rule_id: str = Field(description="The ID of the priority rule.")


class GpuForecastUnit(BaseModel):
    """GPU forecast unit with units count and date"""

    units: int
    date: str


class GpuForecastProfile(BaseModel):
    """GPU forecast for a specific profile"""

    brand: str
    model: str
    profile: str
    now: GpuForecastUnit
    to_create: GpuForecastUnit
    to_destroy: GpuForecastUnit


class BookingPlanResponse(BaseModel):
    """Response model for a booking plan"""

    id: str
    item_type: str
    item_id: str
    subitem_id: str
    units: int
    start: AwareDatetime
    end: AwareDatetime
    user_id: str
    event_type: str
    item: str
