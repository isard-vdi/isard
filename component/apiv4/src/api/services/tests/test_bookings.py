# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for BookingsService — façade over CommonBookings.

The two non-trivial bits are (1) datetime-to-string coercion (the
common helper still wants ISO strings) and (2) the JWT payload
field name (`user_id`) the service forwards to the helper.
"""

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from api.services.bookings import BookingsService

JWT_PAYLOAD = {
    "user_id": "u-admin",
    "category_id": "default",
    "group_id": "default-default",
    "role_id": "admin",
}

START = datetime(2026, 1, 15, 9, 0, tzinfo=timezone.utc)
END = datetime(2026, 1, 15, 10, 0, tzinfo=timezone.utc)


class TestGetUserBookings:
    @patch(
        "api.services.bookings.CommonBookings.get_user_bookings",
        return_value=[],
    )
    def test_forwards_iso_strings_and_user_id(self, mock_get):
        BookingsService.get_user_bookings(START, END, JWT_PAYLOAD)
        args, _ = mock_get.call_args
        # Helper expects strftime("%Y-%m-%dT%H:%M%z") strings, not datetimes
        assert args[0].startswith("2026-01-15T09:00")
        assert args[1].startswith("2026-01-15T10:00")
        assert args[2] == "u-admin"

    @patch("api.services.bookings.CommonBookings.get_user_bookings", return_value=[])
    def test_converts_non_utc_to_utc_before_formatting(self, mock_get):
        # Pacific 01:00+ -> UTC 09:00
        from datetime import timedelta

        pst = timezone(timedelta(hours=-8))
        local_start = START.astimezone(pst)
        BookingsService.get_user_bookings(local_start, END, JWT_PAYLOAD)
        args, _ = mock_get.call_args
        assert args[0].startswith("2026-01-15T09:00")


class TestGetItemBookings:
    @patch(
        "api.services.bookings.CommonBookings.get_item_bookings",
        return_value=[],
    )
    def test_default_return_type_is_all(self, mock_get):
        BookingsService.get_item_bookings(JWT_PAYLOAD, START, END, "desktop", "desk-1")
        kwargs = mock_get.call_args.kwargs
        assert kwargs["returnType"] == "all"
        assert kwargs["item_type"] == "desktop"
        assert kwargs["item_id"] == "desk-1"


class TestCreateBookingEvent:
    @patch("api.services.bookings.CommonBookings.add", return_value={"id": "b1"})
    def test_unwraps_pydantic_model_and_formats_dates(self, mock_add):
        new_event = SimpleNamespace(
            start=START,
            end=END,
            item_type="desktop",
            item_id="desk-1",
            title="Daily slot",
            now=False,
        )
        BookingsService.create_booking_event(JWT_PAYLOAD, new_event)
        kwargs = mock_add.call_args.kwargs
        assert kwargs["payload"] == JWT_PAYLOAD
        assert kwargs["start"].startswith("2026-01-15T09:00")
        assert kwargs["end"].startswith("2026-01-15T10:00")
        assert kwargs["item_type"] == "desktop"
        assert kwargs["item_id"] == "desk-1"
        assert kwargs["title"] == "Daily slot"
        assert kwargs["now"] is False


class TestUpdateBookingEvent:
    @patch("api.services.bookings.CommonBookings.update", return_value={"id": "b1"})
    def test_forwards_title_and_window_to_helper(self, mock_update):
        BookingsService.update_booking_event(JWT_PAYLOAD, "b1", "new title", START, END)
        kwargs = mock_update.call_args.kwargs
        assert kwargs["booking_id"] == "b1"
        assert kwargs["payload"] == JWT_PAYLOAD
        assert kwargs["title"] == "new title"
        assert kwargs["start"] == START
        assert kwargs["end"] == END
