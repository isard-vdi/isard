#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Schema tests for ``CreatePlanRequest`` / ``UpdatePlanRequest`` start
+ end fields.

Old-frontend POST ``/item/reservables-planner`` / PUT
``/item/reservables-planner/{plan_id}/{start}/{end}`` previously took
``start: str`` and ``end: str`` and forwarded the strings to the
``ReservablesPlannerProccess`` model layer, which does datetime
arithmetic via ``ceil_dt``. A naive str triggered ``TypeError:
unsupported operand type(s) for -: 'datetime.datetime' and 'str'`` →
500. The schema now declares ``datetime`` so FastAPI parses the ISO
8601 input at the boundary, plus a field validator coerces naive
datetimes to UTC (some old-frontend pickers serialise without TZ).
"""

from datetime import datetime, timezone

import pytest
from api.schemas.reservables import CreatePlanRequest, UpdatePlanRequest
from pydantic import ValidationError


class TestCreatePlanRequestDatetime:
    def test_accepts_iso_z_suffix(self):
        req = CreatePlanRequest(
            item_type="gpu",
            item_id="card-1",
            subitem_id="profile-A",
            start="2026-05-04T12:00:00Z",
            end="2026-05-04T13:00:00Z",
        )
        assert isinstance(req.start, datetime)
        assert req.start == datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)
        assert req.end.tzinfo is not None

    def test_accepts_iso_with_offset(self):
        req = CreatePlanRequest(
            item_type="gpu",
            item_id="card-1",
            subitem_id="profile-A",
            start="2026-05-04T14:00:00+02:00",
            end="2026-05-04T15:00:00+02:00",
        )
        assert req.start.tzinfo is not None
        # Same instant, different label
        assert req.start == datetime(2026, 5, 4, 12, 0, 0, tzinfo=timezone.utc)

    def test_naive_datetime_coerced_to_utc(self):
        # Some old-frontend code paths serialise without a TZ suffix.
        # The validator must snap to UTC so the planner's ``ceil_dt``
        # arithmetic doesn't trip on a naive value.
        req = CreatePlanRequest(
            item_type="gpu",
            item_id="card-1",
            subitem_id="profile-A",
            start="2026-05-04T12:00:00",
            end="2026-05-04T13:00:00",
        )
        assert req.start.tzinfo == timezone.utc
        assert req.end.tzinfo == timezone.utc

    def test_invalid_iso_string_rejected_with_422_class(self):
        with pytest.raises(ValidationError):
            CreatePlanRequest(
                item_type="gpu",
                item_id="card-1",
                subitem_id="profile-A",
                start="not-a-date",
                end="2026-05-04T13:00:00Z",
            )


class TestUpdatePlanRequestDatetime:
    def test_accepts_iso_z_suffix(self):
        req = UpdatePlanRequest(
            start="2026-05-04T12:00:00Z",
            end="2026-05-04T13:00:00Z",
        )
        assert isinstance(req.start, datetime)
        assert req.start.tzinfo is not None

    def test_naive_datetime_coerced_to_utc(self):
        req = UpdatePlanRequest(
            start="2026-05-04T12:00:00",
            end="2026-05-04T13:00:00",
        )
        assert req.start.tzinfo == timezone.utc
        assert req.end.tzinfo == timezone.utc
