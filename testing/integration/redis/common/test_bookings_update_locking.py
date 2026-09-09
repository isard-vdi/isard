# SPDX-License-Identifier: AGPL-3.0-or-later

"""``BookingsProcessed.update`` under the per-resource lock.

The rest of ``TestBookingsUpdate`` stays a unit test: the not-found path and
the conflict path never reach the lock. These two drive the update through to
completion, and the completion path takes the per-resource Redis lease that
serialises capacity checks — so what they exercise is the real server, and they
belong here rather than beside the mocked cases.

Only the persistence layer is stubbed; the lock is the real one.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


def _make_booking(start_h=11, end_h=12):
    return {
        "id": "b1",
        "item_id": "d1",
        "item_type": "desktop",
        "reservables": {"vgpus": ["NVIDIA-A40-1Q"]},
        "units": 1,
        "start": datetime(2026, 5, 1, start_h, 0, tzinfo=timezone.utc),
        "end": datetime(2026, 5, 1, end_h, 0, tzinfo=timezone.utc),
    }


@pytest.fixture
def update_stub(monkeypatch):
    from isardvdi_common.lib.bookings import bookings as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.BookingsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.BookingsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    return {"mod": mod, "mock_table": mock_table}


class TestBookingsUpdateUnderTheLock:
    def test_updates_when_fits_returns_true(self, update_stub, monkeypatch):
        from isardvdi_common.lib.bookings.reservables_planner import (
            ReservablesPlannerProccess,
        )

        update_stub["mock_table"].return_value.get.return_value.run.return_value = (
            _make_booking()
        )
        monkeypatch.setattr(
            ReservablesPlannerProccess,
            "existing_booking_update_fits",
            classmethod(lambda cls, *a, **kw: True),
        )
        update_stub["mod"].BookingsProcessed.update(
            booking_id="b1",
            payload={"user_id": "u1"},
            title="renamed",
            start="2026-05-01T11:00+0000",
            end="2026-05-01T12:00+0000",
        )
        # Assert the update payload reached r.table("bookings").get("b1").update(...)
        update_chain = update_stub["mock_table"].return_value.get.return_value.update
        update_chain.assert_called()
        call_payload = update_chain.call_args.args[0]
        assert call_payload["title"] == "renamed"
        # start/end were converted to tz-aware datetime
        assert call_payload["start"] == datetime(2026, 5, 1, 11, 0, tzinfo=timezone.utc)
        assert call_payload["end"] == datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)

    def test_passes_new_dates_to_fits_check(self, update_stub, monkeypatch):
        """``BookingsProcessed.update`` must forward ``new_start`` and
        ``new_end`` to ``existing_booking_update_fits`` so the planner
        check happens against the requested window, not the stored one.
        """
        from isardvdi_common.lib.bookings.reservables_planner import (
            ReservablesPlannerProccess,
        )

        update_stub["mock_table"].return_value.get.return_value.run.return_value = (
            _make_booking()
        )

        captured = {}

        def fake_fits(cls, payload, booking, new_start=None, new_end=None):
            captured["new_start"] = new_start
            captured["new_end"] = new_end
            return True

        monkeypatch.setattr(
            ReservablesPlannerProccess,
            "existing_booking_update_fits",
            classmethod(fake_fits),
        )
        update_stub["mod"].BookingsProcessed.update(
            booking_id="b1",
            payload={"user_id": "u1"},
            title="renamed",
            start="2026-05-01T13:00+0000",
            end="2026-05-01T15:00+0000",
        )
        assert captured["new_start"] == datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc)
        assert captured["new_end"] == datetime(2026, 5, 1, 15, 0, tzinfo=timezone.utc)
