# SPDX-License-Identifier: AGPL-3.0-or-later

"""A start-now booking may not end later than the start-now UIs could offer."""

from contextlib import nullcontext
from datetime import datetime, timedelta
from unittest.mock import MagicMock

import pytest
import pytz
from isardvdi_common.helpers.error_base import ErrorBase
from isardvdi_common.lib.bookings import bookings as mod
from rethinkdb.errors import ReqlNonExistenceError

RESERVABLES = {"vgpus": ["NVIDIA-A16-2Q"]}
USER = {"user_id": "u1", "role_id": "user"}
ADMIN = {"user_id": "a1", "role_id": "admin"}


def _priority(forbid_time, max_time):
    return {
        "priority": {"NVIDIA-A16-2Q": 1},
        "forbid_time": forbid_time,
        "max_time": max_time,
        "max_items": 99,
    }


def _fmt(dt):
    return dt.strftime("%Y-%m-%dT%H:%M%z")


@pytest.fixture
def profile_priority(monkeypatch):
    """Sets what ``min_profile_priority`` returns, or raises when given one."""
    holder = {"value": None}

    def fake(cls, reservables):
        if isinstance(holder["value"], Exception):
            raise holder["value"]
        return holder["value"]

    monkeypatch.setattr(
        mod.ReservablesPlannerCompute, "min_profile_priority", classmethod(fake)
    )
    return holder


class TestGetStartNowMaxMinutes:
    def test_non_admin_is_held_to_the_advance_time(self, profile_priority):
        assert (
            mod.BookingsProcessed.get_start_now_max_minutes(
                USER, RESERVABLES, _priority(45, 60)
            )
            == 45
        )

    def test_admin_skips_the_advance_time(self, profile_priority):
        assert (
            mod.BookingsProcessed.get_start_now_max_minutes(
                ADMIN, RESERVABLES, _priority(1, 90)
            )
            == 90
        )

    def test_the_profile_rule_wins_when_larger(self, profile_priority):
        profile_priority["value"] = _priority(90, 600)
        assert (
            mod.BookingsProcessed.get_start_now_max_minutes(
                USER, RESERVABLES, _priority(120, 30)
            )
            == 90
        )

    def test_the_user_rule_wins_when_larger(self, profile_priority):
        profile_priority["value"] = _priority(10, 600)
        assert (
            mod.BookingsProcessed.get_start_now_max_minutes(
                USER, RESERVABLES, _priority(120, 40)
            )
            == 40
        )

    def test_default_rows_give_an_admin_the_twelve_hour_cap(self, profile_priority):
        # `default admins` for the user, `default` for the profile.
        profile_priority["value"] = _priority(0, 60)
        assert (
            mod.BookingsProcessed.get_start_now_max_minutes(
                ADMIN, RESERVABLES, _priority(1, 999999)
            )
            == mod.ReservablesPlannerProccess.MAX_BOOKING_TIME
        )

    @pytest.mark.parametrize("max_time", [0, None])
    def test_no_max_time_for_the_user_allows_nothing(self, profile_priority, max_time):
        profile_priority["value"] = _priority(600, 600)
        assert (
            mod.BookingsProcessed.get_start_now_max_minutes(
                ADMIN, RESERVABLES, _priority(600, max_time)
            )
            == 0
        )

    def test_a_profile_rule_without_rows_falls_back_to_the_user(self, profile_priority):
        profile_priority["value"] = ReqlNonExistenceError(
            "Cannot take the min of an empty stream."
        )
        assert (
            mod.BookingsProcessed.get_start_now_max_minutes(
                USER, RESERVABLES, _priority(50, 60)
            )
            == 50
        )


class TestAddStartNowLimit:
    @pytest.fixture
    def add_stub(self, monkeypatch, profile_priority):
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
        monkeypatch.setattr(mod, "resource_lock", lambda *a, **kw: nullcontext())
        monkeypatch.setattr(mod.Helpers, "owns_domain_id", lambda **kw: None)
        monkeypatch.setattr(
            mod.BookingsHelper,
            "_get_reservables",
            lambda item_type, item_id: (RESERVABLES, 1, "desktop"),
        )
        priority = {"value": _priority(120, 60)}
        monkeypatch.setattr(
            mod.BookingsProcessed,
            "get_user_priority",
            classmethod(lambda cls, *a: priority["value"]),
        )
        monkeypatch.setattr(
            mod.BookingsProcessed,
            "get_total_user_bookings_count",
            classmethod(lambda cls, user_id: 0),
        )
        monkeypatch.setattr(
            mod.ReservablesPlannerProccess,
            "new_booking_plans",
            classmethod(
                lambda cls, payload, booking: {
                    "vgpus": [
                        {
                            "id": "plan1",
                            "item_id": "card1",
                            "subitem_id": "NVIDIA-A16-2Q",
                            "units_booked": 1,
                        }
                    ]
                }
            ),
        )
        monkeypatch.setattr(
            mod.SchedulerHelper, "bookings_schedule", lambda *a, **kw: None
        )
        return {"insert": mock_table.return_value.insert, "priority": priority}

    def _add(self, minutes, now=True, start=None):
        start = start or datetime.now(pytz.UTC)
        return mod.BookingsProcessed.add(
            USER,
            _fmt(start),
            _fmt(start + timedelta(minutes=minutes)),
            "desktop",
            "d1",
            now=now,
        )

    def test_an_end_within_the_limit_is_booked(self, add_stub):
        self._add(55)
        assert add_stub["insert"].call_count == 1

    def test_an_end_past_the_limit_is_refused(self, add_stub):
        with pytest.raises(ErrorBase) as exc:
            self._add(120)
        assert exc.value.error["description_code"] == "booking_exceeds_max_time"
        assert add_stub["insert"].call_count == 0

    def test_the_profile_rule_can_allow_the_end(self, add_stub, profile_priority):
        add_stub["priority"]["value"] = _priority(120, 30)
        profile_priority["value"] = _priority(90, 600)
        self._add(80)
        assert add_stub["insert"].call_count == 1

    def test_a_calendar_booking_is_not_held_to_it(self, add_stub):
        self._add(600, now=False, start=datetime.now(pytz.UTC) + timedelta(days=1))
        assert add_stub["insert"].call_count == 1
