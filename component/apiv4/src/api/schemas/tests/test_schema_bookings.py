# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for api/schemas/bookings.py — request models and the enum /
literal / datetime guards that protect the bookings endpoints.
"""

from datetime import datetime, timezone

import pytest
from api.schemas.bookings import (
    AvailabilityResponse,
    CreateBookingEventRequest,
    ItemBookingsResponse,
    UpdateBookingEventRequest,
    UserBookingPlan,
    UserBookingResponse,
)
from pydantic import ValidationError


class TestCreateBookingEventRequest:
    _valid = {
        "item_id": "deployment-1",
        "item_type": "deployment",
        "start": "2026-01-15T09:00:00+00:00",
        "end": "2026-01-15T10:00:00+00:00",
    }

    def test_accepts_valid_desktop(self):
        r = CreateBookingEventRequest(**{**self._valid, "item_type": "desktop"})
        assert r.item_type == "desktop"
        assert isinstance(r.start, datetime)

    def test_item_type_defaults_to_desktop(self):
        payload = {k: v for k, v in self._valid.items() if k != "item_type"}
        assert CreateBookingEventRequest(**payload).item_type == "desktop"

    def test_rejects_unknown_item_type(self):
        with pytest.raises(ValidationError):
            CreateBookingEventRequest(**{**self._valid, "item_type": "template"})

    def test_title_defaults_to_empty_string(self):
        assert CreateBookingEventRequest(**self._valid).title == ""

    def test_now_defaults_false(self):
        assert CreateBookingEventRequest(**self._valid).now is False

    def test_item_id_required(self):
        payload = {k: v for k, v in self._valid.items() if k != "item_id"}
        with pytest.raises(ValidationError):
            CreateBookingEventRequest(**payload)

    def test_coerces_iso_string_to_datetime(self):
        r = CreateBookingEventRequest(**self._valid)
        assert r.start.tzinfo is not None


class TestUpdateBookingEventRequest:
    _valid = {
        "start": "2026-01-15T09:00:00+00:00",
        "end": "2026-01-15T10:00:00+00:00",
    }

    def test_minimal_payload_ok(self):
        r = UpdateBookingEventRequest(**self._valid)
        assert r.title == ""
        assert r.element_type is None

    def test_accepts_deprecated_element_type(self):
        r = UpdateBookingEventRequest(**{**self._valid, "element_type": "desktop"})
        assert r.element_type.value == "desktop"

    def test_rejects_bad_element_type(self):
        with pytest.raises(ValidationError):
            UpdateBookingEventRequest(**{**self._valid, "element_type": "banana"})

    def test_start_and_end_required(self):
        with pytest.raises(ValidationError):
            UpdateBookingEventRequest()


class TestUserBookingResponse:
    _base = {
        "id": "b1",
        "item_id": "desk-1",
        "item_type": "desktop",
        "units": 1,
        "reservables": {"vgpus": ["gpu-1"]},
        "start": "2026-01-15T09:00:00+00:00",
        "end": "2026-01-15T10:00:00+00:00",
        "title": "Booking",
        "user_id": "u1",
        "editable": True,
        "event_type": "event",
        "plans": [],
    }

    def test_valid_booking_response(self):
        assert UserBookingResponse(**self._base).item_type == "desktop"

    def test_item_type_literal_enforced(self):
        with pytest.raises(ValidationError):
            UserBookingResponse(**{**self._base, "item_type": "media"})

    def test_event_type_literal_enforced(self):
        with pytest.raises(ValidationError):
            UserBookingResponse(**{**self._base, "event_type": "random"})

    def test_aware_datetime_required(self):
        # Naive datetime (no tz) should fail AwareDatetime validation
        with pytest.raises(ValidationError):
            UserBookingResponse(**{**self._base, "start": "2026-01-15T09:00:00"})

    def test_plans_accepts_list_of_plans(self):
        plan = UserBookingPlan(
            plan_id="p1",
            priority=1,
            item_id="i1",
            subitem_id="s1",
            units_booked=2,
        )
        r = UserBookingResponse(**{**self._base, "plans": [plan]})
        assert r.plans[0].units_booked == 2


class TestAvailabilityResponse:
    _valid = {
        "start": datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc),
        "end": datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc),
        "event_type": "available",
        "units": "Enough",
    }

    def test_accepts_enough_literal(self):
        assert AvailabilityResponse(**self._valid).units == "Enough"

    def test_accepts_integer_units(self):
        assert AvailabilityResponse(**{**self._valid, "units": 5}).units == 5

    def test_rejects_random_string_units(self):
        # The Literal["Enough"] | int union rejects arbitrary strings.
        with pytest.raises(ValidationError):
            AvailabilityResponse(**{**self._valid, "units": "lots"})

    def test_event_type_restricted(self):
        with pytest.raises(ValidationError):
            AvailabilityResponse(**{**self._valid, "event_type": "event"})


class TestItemBookingsResponse:
    def test_accepts_mixed_booking_and_availability(self):
        booking = {
            "id": "b1",
            "item_id": "d1",
            "item_type": "desktop",
            "units": 1,
            "reservables": {"vgpus": []},
            "start": "2026-01-15T09:00:00+00:00",
            "end": "2026-01-15T10:00:00+00:00",
            "title": "T",
            "user_id": "u1",
            "editable": True,
            "event_type": "event",
            "plans": [],
        }
        availability = {
            "start": "2026-01-15T11:00:00+00:00",
            "end": "2026-01-15T12:00:00+00:00",
            "event_type": "available",
            "units": 3,
        }
        resp = ItemBookingsResponse(root=[booking, availability])
        assert len(resp.root) == 2
