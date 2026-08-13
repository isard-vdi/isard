#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``Bookings.add`` under CONCURRENCY: capacity and quota are hard ceilings.

The planner race (``test_planner_concurrent_plans``) has a twin one layer up.
``add`` counts the user's bookings for the ``max_items`` quota, then asks
``new_booking_plans`` whether the requested profiles still have room -- and both
answers are read from rows that its own insert is about to add to. Fired
together, N requests each measure a world without the other N-1, all N find the
last free unit, and all N take it.

What is stubbed and what is not: the capacity ARITHMETIC is stubbed (a counter of
the bookings already stored for the profile, which is what
``booking_provisioning`` computes the long way), because none of it is under
test here. What is real is the thing that is: whether ``add`` reads and writes
that shared state atomically. The exclusion is the production one -- an actual
redis lease taken by ``resource_lock``.
"""

import threading
import time
import uuid
from datetime import datetime, timedelta

import pytest
import pytz
import redis as redis_lib
from isardvdi_common.connections.redis_urls import rq_url
from isardvdi_common.lib.bookings import bookings as mod

PROFILE_ID = "NVIDIA-L40S-8Q"
REQUESTS = 8

# Simulated cost of the availability computation, which in production is several
# indexed queries plus interval arithmetic. Without it the check->insert window
# is narrower than the thread stagger and the race stops being reproducible.
COMPUTE_LATENCY_S = 0.01


def _redis_or_fail():
    conn = redis_lib.from_url(rq_url(), socket_connect_timeout=5, socket_timeout=5)
    try:
        conn.ping()
    except Exception as error:
        from isardvdi_common.redis_test_gate import redis_required

        redis_required(f"no Redis for the booking concurrency test: {error}")
    return conn


class _Store:
    """The ``bookings`` rows, with per-operation (not cross-operation) atomicity."""

    def __init__(self):
        self.rows = []
        self._lock = threading.Lock()

    def insert(self, row):
        with self._lock:
            self.rows.append(dict(row))

    def count_for_profile(self, profile):
        with self._lock:
            return len(
                [
                    row
                    for row in self.rows
                    if profile in (row.get("reservables") or {}).get("vgpus", [])
                ]
            )

    def profile_for(self, item_id):
        """Which profile a desktop asks for.

        Shared by default (everyone competes for the same capacity); one profile
        per desktop when the test is about requests that should NOT contend.
        """
        return f"{PROFILE_ID}-{item_id}" if self.distinct_profiles else PROFILE_ID

    def count_for_user(self, user_id):
        with self._lock:
            return len([row for row in self.rows if row.get("user_id") == user_id])


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def store(monkeypatch):
    """``add`` wired to an in-memory bookings table, capacity 1 by default."""
    _redis_or_fail()
    state = _Store()
    state.total_units = 1
    state.max_items = 1000
    state.distinct_profiles = False

    monkeypatch.setattr(
        mod.BookingsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.BookingsProcessed), "_rdb_connection", property(lambda self: None)
    )

    class _R:
        def table(self, name):
            assert name == "bookings", f"unexpected table {name}"
            return _Inserting()

    class _Inserting:
        def insert(self, row):
            state.insert(row)
            return _Ran()

    class _Ran:
        def run(self, _conn):
            return {"inserted": 1}

    monkeypatch.setattr(mod, "r", _R())
    monkeypatch.setattr(
        mod.BookingsHelper,
        "_get_reservables",
        staticmethod(
            lambda item_type, item_id: (
                {"vgpus": [state.profile_for(item_id)]},
                1,
                "a desktop",
            )
        ),
    )
    monkeypatch.setattr(
        mod.BookingsProcessed,
        "get_user_priority",
        classmethod(
            lambda cls, payload, item_type, item_id: {
                "max_items": state.max_items,
                "priority": {state.profile_for(item_id): 50},
            }
        ),
    )
    monkeypatch.setattr(
        mod.BookingsProcessed,
        "get_total_user_bookings_count",
        classmethod(lambda cls, user_id: state.count_for_user(user_id)),
    )

    def _new_booking_plans(payload, booking):
        # What booking_provisioning does in essence: measure what the existing
        # bookings already consume, and hand back a plan only if a unit is left.
        # The count is taken BEFORE the latency, exactly as a real query answers
        # from the state it found on arrival, not on reply.
        profile = booking["reservables"]["vgpus"][0]
        taken = state.count_for_profile(profile)
        time.sleep(COMPUTE_LATENCY_S)
        if taken >= state.total_units:
            return {}
        return {
            profile: [
                {
                    "id": f"plan-{uuid.uuid4()}",
                    "item_id": "card-1",
                    "subitem_id": profile,
                    "units_booked": 1,
                }
            ]
        }

    monkeypatch.setattr(
        mod.ReservablesPlannerProccess,
        "new_booking_plans",
        staticmethod(_new_booking_plans),
    )
    monkeypatch.setattr(
        mod.SchedulerHelper,
        "bookings_schedule",
        staticmethod(lambda *a, **kw: None),
    )
    return state


def _payload(user_id):
    return {"user_id": user_id, "role_id": "user", "category_id": "default"}


def _race(count, user_for):
    barrier = threading.Barrier(count)
    outcomes = [None] * count
    start = (datetime.now(pytz.utc) + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M%z")
    end = (datetime.now(pytz.utc) + timedelta(days=1, hours=2)).strftime(
        "%Y-%m-%dT%H:%M%z"
    )

    def worker(index):
        barrier.wait()
        try:
            outcomes[index] = (
                "ok",
                mod.BookingsProcessed.add(
                    _payload(user_for(index)), start, end, "desktop", f"desktop-{index}"
                ),
            )
        except Exception as error:
            outcomes[index] = ("error", error)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads), "a worker deadlocked"
    return outcomes


class TestConcurrentBookingsRespectCapacity:
    def test_only_total_units_bookings_win_a_one_unit_profile(self, store):
        """8 users, 8 desktops, 1 unit of capacity -> exactly 1 booking.

        Fails on the unguarded code with all 8 committed against a total_units
        of 1 -- every desktop then holds a booking the hardware cannot honour,
        and the overflow only surfaces at start time as a failed domain.
        """
        outcomes = _race(REQUESTS, lambda index: f"user-{uuid.uuid4()}")

        assert len(store.rows) <= store.total_units, (
            f"{len(store.rows)} bookings committed against a total_units of "
            f"{store.total_units}"
        )
        assert len(store.rows) == 1
        assert len([o for o in outcomes if o[0] == "ok"]) == 1
        for _tag, error in [o for o in outcomes if o[0] == "error"]:
            assert getattr(error, "status_code", None) == 409, error

    def test_capacity_of_three_admits_exactly_three(self, store):
        """Not "one wins" but "capacity wins": the ceiling is total_units."""
        store.total_units = 3
        _race(REQUESTS, lambda index: f"user-{uuid.uuid4()}")

        assert len(store.rows) == 3

    def test_max_items_quota_is_not_overrun_by_a_racing_user(self, store):
        """The quota count has the same shape, so it needs the same section.

        One user, plenty of capacity, ``max_items`` of 2: firing 8 at once must
        still leave them with 2. Unguarded, all 8 read a count of 0.
        """
        store.total_units = 100
        store.max_items = 2
        user = f"user-{uuid.uuid4()}"
        outcomes = _race(REQUESTS, lambda index: user)

        assert (
            len(store.rows) == 2
        ), f"user holds {len(store.rows)} bookings against a max_items of 2"
        assert len([o for o in outcomes if o[0] == "ok"]) == 2
        for _tag, error in [o for o in outcomes if o[0] == "error"]:
            assert getattr(error, "status_code", None) == 428, error


class TestBookingsAreNotSerialisedGlobally:
    def test_different_users_and_profiles_do_not_queue(self, store):
        """Capacity is per profile and quota per user, so unrelated bookings run
        together. A single global lease would pass every test above and quietly
        turn every booking into a queue; this is what tells the two apart."""
        store.distinct_profiles = True  # nobody competes with anybody

        started = time.monotonic()
        outcomes = _race(REQUESTS, lambda index: f"user-{uuid.uuid4()}")
        elapsed = time.monotonic() - started

        assert len([o for o in outcomes if o[0] == "ok"]) == REQUESTS
        # Each section costs one COMPUTE_LATENCY_S. Queued: ~REQUESTS x that.
        assert (
            elapsed < REQUESTS * COMPUTE_LATENCY_S
        ), f"{elapsed:.3f}s for {REQUESTS} independent bookings is serial-shaped"
