#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Schema tests for ``CreateBookingEventRequest`` / ``UpdateBookingEventRequest``
start + end fields.

Pin Bug 5 — apiv4-integration audit: the booking event schemas previously
declared ``start`` / ``end`` as ``datetime`` without the ``_ensure_aware_utc``
validator that ``CreatePlanRequest`` already had. Naive datetimes from
old-frontend pickers slipped through to ``BookingsProcessed.add`` /
``update`` where ``datetime.strptime(..., "%Y-%m-%dT%H:%M%z")`` rejects them
with a misleading ``ValueError`` surfaced as a 500. The validators added
in this fix coerce naive datetimes to UTC at the schema boundary, mirroring
the reservable-plan path.
"""

from datetime import datetime, timezone

import pytest
from api.schemas.bookings import CreateBookingEventRequest, UpdateBookingEventRequest
from pydantic import ValidationError


class TestCreateBookingEventRequestDatetime:
    def test_accepts_iso_z_suffix(self):
        req = CreateBookingEventRequest(
            item_id="d1",
            item_type="desktop",
            start="2026-05-04T12:00:00Z",
            end="2026-05-04T13:00:00Z",
        )
        assert isinstance(req.start, datetime)
        assert req.start == datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        assert req.end.tzinfo is not None

    def test_accepts_iso_with_offset(self):
        req = CreateBookingEventRequest(
            item_id="d1",
            start="2026-05-04T14:00:00+02:00",
            end="2026-05-04T15:00:00+02:00",
        )
        assert req.start.tzinfo is not None
        # Same instant, different label
        assert req.start == datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)

    def test_naive_datetime_coerced_to_utc(self):
        """Pin Bug 5 — naive datetimes from old-frontend must be coerced
        at the schema boundary. Without this validator, the service-layer
        ``strftime("%Y-%m-%dT%H:%M%z")`` call raises ``ValueError`` on a
        naive datetime and the route returns 500.
        """
        req = CreateBookingEventRequest(
            item_id="d1",
            start="2026-05-04T12:00:00",
            end="2026-05-04T13:00:00",
        )
        assert req.start.tzinfo == timezone.utc
        assert req.end.tzinfo == timezone.utc

    def test_invalid_iso_rejected(self):
        with pytest.raises(ValidationError):
            CreateBookingEventRequest(
                item_id="d1",
                start="not-a-date",
                end="2026-05-04T13:00:00Z",
            )

    def test_default_item_type_is_desktop(self):
        req = CreateBookingEventRequest(
            item_id="d1",
            start="2026-05-04T12:00:00Z",
            end="2026-05-04T13:00:00Z",
        )
        assert req.item_type == "desktop"

    def test_now_flag_defaults_false(self):
        req = CreateBookingEventRequest(
            item_id="d1",
            start="2026-05-04T12:00:00Z",
            end="2026-05-04T13:00:00Z",
        )
        assert req.now is False


class TestUpdateBookingEventRequestDatetime:
    def test_accepts_iso_z_suffix(self):
        req = UpdateBookingEventRequest(
            title="renamed",
            start="2026-05-04T12:00:00Z",
            end="2026-05-04T13:00:00Z",
        )
        assert isinstance(req.start, datetime)
        assert req.start.tzinfo is not None

    def test_naive_datetime_coerced_to_utc(self):
        req = UpdateBookingEventRequest(
            title="renamed",
            start="2026-05-04T12:00:00",
            end="2026-05-04T13:00:00",
        )
        assert req.start.tzinfo == timezone.utc
        assert req.end.tzinfo == timezone.utc

    def test_element_type_optional(self):
        req = UpdateBookingEventRequest(
            title="renamed",
            start="2026-05-04T12:00:00Z",
            end="2026-05-04T13:00:00Z",
        )
        assert req.element_type is None
