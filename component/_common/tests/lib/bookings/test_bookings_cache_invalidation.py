#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A booking write must invalidate the TTL cache the desktop-start gate reads."""

import uuid
from datetime import datetime, timedelta

import pytest
import pytz
from isardvdi_common.lib.bookings import bookings as mod


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


class _World:
    """The rows the cached query would find, mutable by the test."""

    def __init__(self):
        self.rows = []
        self.queries = 0


@pytest.fixture
def world(monkeypatch):
    state = _World()

    # ``add`` takes a resource_lock, which talks to a real redis. What is under
    # test is cache invalidation, not the lock, and a unit job has no redis.
    monkeypatch.setattr(mod, "resource_lock", lambda *keys: _Ctx())

    monkeypatch.setattr(
        mod.BookingsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.BookingsProcessed), "_rdb_connection", property(lambda self: None)
    )

    class _Query:
        def get_all(self, *a, **kw):
            return self

        def filter(self, *a, **kw):
            return self

        def order_by(self, *a, **kw):
            return self

        def get(self, *a, **kw):
            return self

        def delete(self, *a, **kw):
            return self

        def insert(self, row):
            state.rows.append(row)
            return self

        def update(self, *a, **kw):
            return self

        def run(self, _conn):
            state.queries += 1
            return list(state.rows)

    class _R:
        def table(self, _name):
            return _Query()

        def now(self):
            return datetime.now(pytz.utc)

    monkeypatch.setattr(mod, "r", _R())
    mod.BookingsProcessed.clear_get_cached_desktop_bookings_cache()
    mod.BookingsProcessed.clear_get_cached_deployment_bookings_cache()
    return state


class TestBookingsCacheInvalidation:
    def test_cache_serves_a_second_read_without_querying_again(self, world):
        """Guard: the cache really is a cache, so the test below means something."""
        mod.BookingsProcessed.get_cached_desktop_bookings("desk-1")
        before = world.queries
        mod.BookingsProcessed.get_cached_desktop_bookings("desk-1")
        assert world.queries == before

    def test_clearing_the_cache_makes_the_next_read_fresh(self, world):
        mod.BookingsProcessed.get_cached_desktop_bookings("desk-1")
        world.rows.append({"id": "b-1", "item_id": "desk-1"})
        mod.BookingsProcessed.clear_get_cached_desktop_bookings_cache()
        assert mod.BookingsProcessed.get_cached_desktop_bookings("desk-1") == [
            {"id": "b-1", "item_id": "desk-1"}
        ]

    def test_a_new_booking_is_visible_immediately(self, world, monkeypatch):
        """The one that was broken: book, then read, within the TTL window."""
        desktop_id = "desk-" + uuid.uuid4().hex[:8]
        profile = "NVIDIA-TESTCARD-4Q"

        monkeypatch.setattr(
            mod.BookingsHelper,
            "_get_reservables",
            staticmethod(
                lambda item_type, item_id: ({"vgpus": [profile]}, 1, "a desktop")
            ),
        )
        monkeypatch.setattr(
            mod.BookingsProcessed,
            "get_user_priority",
            classmethod(
                lambda cls, payload, item_type, item_id: {
                    "max_items": 10,
                    "priority": {profile: 50},
                }
            ),
        )
        monkeypatch.setattr(
            mod.BookingsProcessed,
            "get_total_user_bookings_count",
            classmethod(lambda cls, user_id: 0),
        )
        monkeypatch.setattr(
            mod.ReservablesPlannerProccess,
            "new_booking_plans",
            staticmethod(
                lambda payload, booking: {
                    profile: [
                        {
                            "id": "plan-1",
                            "item_id": "card-1",
                            "subitem_id": profile,
                            "units_booked": 1,
                        }
                    ]
                }
            ),
        )
        monkeypatch.setattr(
            mod.SchedulerHelper,
            "bookings_schedule",
            staticmethod(lambda *a, **kw: None),
        )
        monkeypatch.setattr(
            mod.Helpers,
            "owns_domain_id",
            classmethod(lambda cls, payload, domain_id: None),
        )

        # The gate reads the cache before the booking exists: nothing yet.
        assert mod.BookingsProcessed.get_cached_desktop_bookings(desktop_id) == []

        start = datetime.now(pytz.utc) + timedelta(minutes=10)
        end = start + timedelta(hours=1)
        mod.BookingsProcessed.add(
            {"user_id": "u-1", "role_id": "user", "category_id": "default"},
            start.strftime("%Y-%m-%dT%H:%M%z"),
            end.strftime("%Y-%m-%dT%H:%M%z"),
            "desktop",
            desktop_id,
        )

        assert mod.BookingsProcessed.get_cached_desktop_bookings(desktop_id), (
            "the booking just created is invisible to the start gate: the TTL "
            "cache was not invalidated by add()"
        )
