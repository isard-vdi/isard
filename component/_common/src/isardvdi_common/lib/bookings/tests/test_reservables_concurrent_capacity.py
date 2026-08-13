#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""The same read-then-write race in the capacity ACCOUNTING, not the booking.

Two more instances of the planner defect, one card-shaped and one profile-shaped:

* ``enable_subitem`` reads ``gpus.profiles_enabled``, edits the list in python and
  writes the whole list back. Enable two different profiles on one card at once
  and the second write is computed from a list that predates the first: a
  textbook lost update, and the profile that vanishes is one an admin was told
  had been enabled.
* ``recompute_total_units`` derives ``total_units`` by COUNTING the cards that
  enable a profile. Two writers -- the admin enabling a card and the hypervisor
  reconcile that recomputes on registration -- each count the world before the
  other's card landed, and both store their stale product. The profile then
  advertises a fraction of its real capacity, so bookings are refused against
  hardware that is sitting idle.

Neither shows up in a sequential test: run either pair one after the other and
the answer is right every time.
"""

import copy
import threading
import time
import uuid

import pytest
import redis as redis_lib
from isardvdi_common.connections.redis_urls import rq_url
from isardvdi_common.lib.bookings import reservables as mod

PROFILE_ID = "NVIDIA-L40S-8Q"
UNITS_PER_CARD = 4
CARDS = 6
QUERY_LATENCY_S = 0.01


def _redis_or_fail():
    conn = redis_lib.from_url(rq_url(), socket_connect_timeout=5, socket_timeout=5)
    try:
        conn.ping()
    except Exception as error:
        from isardvdi_common.redis_test_gate import redis_required

        redis_required(f"no Redis for the reservables concurrency test: {error}")
    return conn


class _Db:
    """``gpus`` + ``reservables_vgpus``, atomic per operation only.

    Every read DEEP-copies. A shallow copy would hand all the racing callers the
    same ``profiles_enabled`` list object, so their ``.append`` calls would
    accumulate into one list and the lost update would disappear -- the harness
    would then quietly certify the broken code. RethinkDB deserializes a fresh
    object per reply; this matches that.
    """

    def __init__(self):
        self.gpus = {}
        self.reservables = {}
        # Per-thread query latency, so a test can pin an interleaving instead of
        # hoping for one (real queries do not all take the same time either).
        self.latency = {}
        self._lock = threading.Lock()

    def sleep(self):
        time.sleep(self.latency.get(threading.current_thread().name, QUERY_LATENCY_S))

    def card(self, card_id):
        with self._lock:
            row = self.gpus.get(card_id)
            return copy.deepcopy(row) if row else None

    def set_card(self, card_id, patch):
        with self._lock:
            self.gpus.setdefault(card_id, {}).update(copy.deepcopy(patch))
            return {"replaced": 1}

    def cards_enabling(self, profile):
        with self._lock:
            return [
                copy.deepcopy(row)
                for row in self.gpus.values()
                if profile in (row.get("profiles_enabled") or [])
            ]

    def reservable(self, reservable_id):
        with self._lock:
            row = self.reservables.get(reservable_id)
            return copy.deepcopy(row) if row else None

    def set_reservable(self, reservable_id, patch):
        with self._lock:
            self.reservables.setdefault(reservable_id, {}).update(copy.deepcopy(patch))
            return {"replaced": 1}


class _GpusQuery:
    """Only the shapes enable_subitem / recompute_total_units actually issue."""

    def __init__(self, db, card_id=None, profile=None, physical_only=False):
        self._db = db
        self._card_id = card_id
        self._profile = profile
        self._physical_only = physical_only

    def get(self, card_id):
        return _GpusQuery(self._db, card_id=card_id)

    def filter(self, predicate):
        # The production lambdas are `gpu["profiles_enabled"].contains(id)` and
        # that ANDed with `physical_device != None`; the sentinel row below
        # records which of the two was built.
        probe = predicate(_RowProbe())
        return _GpusQuery(
            self._db, profile=probe.profile, physical_only=probe.physical_only
        )

    def update(self, patch):
        return _Ran(self._db, lambda: self._db.set_card(self._card_id, patch))

    def count(self):
        return _Ran(self._db, self._rows, wrap=len)

    def _rows(self):
        rows = self._db.cards_enabling(self._profile)
        if self._physical_only:
            rows = [row for row in rows if row.get("physical_device") is not None]
        return rows

    def run(self, _conn):
        # Read the state as of NOW, then pay the round trip (see the planner
        # test: sampling after the delay hides the race).
        result = self._db.card(self._card_id) if self._card_id else self._rows()
        self._db.sleep()
        return result


class _ReservablesQuery:
    def __init__(self, db, reservable_id=None):
        self._db = db
        self._id = reservable_id

    def get(self, reservable_id):
        return _ReservablesQuery(self._db, reservable_id)

    def update(self, patch):
        return _Ran(self._db, lambda: self._db.set_reservable(self._id, patch))

    def run(self, _conn):
        return self._db.reservable(self._id)


class _Ran:
    def __init__(self, db, fn, wrap=None):
        self._db = db
        self._fn = fn
        self._wrap = wrap

    def run(self, _conn):
        result = self._fn()
        self._db.sleep()
        return self._wrap(result) if self._wrap else result


class _RowProbe:
    """Records what a production filter lambda asked about."""

    def __init__(self):
        self.profile = None
        self.physical_only = False

    def __getitem__(self, key):
        self._key = key
        return self

    def contains(self, value):
        self.profile = value
        return self

    def default(self, _value):
        return self

    def ne(self, _value):
        self.physical_only = True
        return self

    def __and__(self, other):
        return self


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def db(monkeypatch):
    _redis_or_fail()
    state = _Db()

    class _R:
        def table(self, name):
            if name == "gpus":
                return _GpusQuery(state)
            if name == "reservables_vgpus":
                return _ReservablesQuery(state)
            raise AssertionError(f"unexpected table {name}")

    monkeypatch.setattr(mod, "r", _R())
    monkeypatch.setattr(
        mod.ResourceItemsGpus, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.ResourceItemsGpus), "_rdb_connection", property(lambda self: None)
    )
    monkeypatch.setattr(
        mod.ApiAdmin,
        "clear_admin_table_list_cache",
        classmethod(lambda cls, table: None),
    )
    return state


def _run_together(fns):
    barrier = threading.Barrier(len(fns))
    errors = []

    def worker(fn):
        barrier.wait()
        try:
            fn()
        except Exception as error:  # noqa: BLE001 - reported, not swallowed
            errors.append(error)

    threads = [threading.Thread(target=worker, args=(fn,)) for fn in fns]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads), "a worker deadlocked"
    assert not errors, errors
    return errors


class TestEnableSubitemDoesNotLoseProfiles:
    def test_two_profiles_enabled_at_once_on_one_card_both_survive(
        self, db, monkeypatch
    ):
        """Read-edit-write on ``profiles_enabled``: neither enable may vanish.

        Fails on the unguarded code with one of the two profiles missing -- the
        admin sees a green PUT and an unchanged card.
        """
        # The downstream reservable bookkeeping is exercised by the other class.
        monkeypatch.setattr(
            mod.ResourceItemsGpus,
            "add_reservable_vgpu",
            classmethod(lambda cls, item_id, subitem_id: None),
        )
        card_id = f"card-{uuid.uuid4()}"
        db.gpus[card_id] = {"id": card_id, "profiles_enabled": [], "physical_device": 1}
        profiles = [f"NVIDIA-L40S-{index}Q" for index in range(CARDS)]

        _run_together(
            [
                (
                    lambda profile=profile: mod.ResourceItemsGpus.enable_subitem(
                        card_id, profile, True
                    )
                )
                for profile in profiles
            ]
        )

        enabled = db.card(card_id)["profiles_enabled"]
        assert sorted(enabled) == sorted(profiles), (
            f"only {len(enabled)} of {len(profiles)} concurrent enables survived: "
            f"{sorted(enabled)}"
        )


class TestTotalUnitsSurvivesConcurrentRecompute:
    def test_a_slow_recompute_cannot_overwrite_a_newer_count(self, db):
        """The lost update spelled out, with the interleaving pinned.

        ``slow`` counts the cards first (it sees CARDS-1, the world before the
        new card) but its count query is deliberately slow to come back;
        meanwhile ``fast`` brings the last card in, counts CARDS and stores the
        right capacity. ``slow`` then writes the number it measured long ago.

        Unguarded that is the LAST write, so the profile is left advertising
        (CARDS-1) x units of a fleet that has CARDS -- capacity that exists but
        can never be booked. Guarded, ``fast`` cannot get between ``slow``'s
        count and its write, so whoever writes last measured last.
        """
        db.reservables[PROFILE_ID] = {"id": PROFILE_ID, "units": UNITS_PER_CARD}
        card_ids = [f"card-{uuid.uuid4()}" for _ in range(CARDS)]
        for index, card_id in enumerate(card_ids):
            db.gpus[card_id] = {
                "id": card_id,
                # Every card but the last already realizes the profile.
                "profiles_enabled": [] if index == CARDS - 1 else [PROFILE_ID],
                "physical_device": card_id,
            }
        # `slow`'s queries take long enough that `fast` runs entirely inside its
        # count->write gap; `fast`'s are instant.
        db.latency = {"slow": 0.15, "fast": 0.0}

        def slow():
            mod.ResourceItemsGpus.recompute_total_units(PROFILE_ID)

        def fast():
            time.sleep(0.03)  # let `slow` take its count first
            db.set_card(card_ids[-1], {"profiles_enabled": [PROFILE_ID]})
            mod.ResourceItemsGpus.recompute_total_units(PROFILE_ID)

        threads = [
            threading.Thread(target=slow, name="slow"),
            threading.Thread(target=fast, name="fast"),
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=60)
        assert not any(thread.is_alive() for thread in threads), "a worker deadlocked"

        expected = CARDS * UNITS_PER_CARD
        stored = db.reservable(PROFILE_ID)["total_units"]
        assert stored == expected, (
            f"total_units stored as {stored}, but {CARDS} cards x {UNITS_PER_CARD} "
            f"units = {expected}; a stale count won the last write"
        )

    def test_recomputes_for_different_profiles_do_not_queue(self, db):
        """Per profile, not global: unrelated profiles recompute together."""
        profiles = [f"NVIDIA-L40S-{index}Q" for index in range(CARDS)]
        for profile in profiles:
            db.reservables[profile] = {"id": profile, "units": UNITS_PER_CARD}
            card_id = f"card-{uuid.uuid4()}"
            db.gpus[card_id] = {
                "id": card_id,
                "profiles_enabled": [profile],
                "physical_device": card_id,
            }

        started = time.monotonic()
        _run_together(
            [
                (
                    lambda profile=profile: mod.ResourceItemsGpus.recompute_total_units(
                        profile
                    )
                )
                for profile in profiles
            ]
        )
        elapsed = time.monotonic() - started

        # Three queries each; queued that is ~CARDS x 3 x latency.
        assert elapsed < CARDS * 3 * QUERY_LATENCY_S, (
            f"{elapsed:.3f}s for {CARDS} unrelated profiles is serial-shaped; the "
            "critical section is too coarse"
        )
        for profile in profiles:
            assert db.reservable(profile)["total_units"] == UNITS_PER_CARD
