#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``add_plan`` under CONCURRENCY: only one plan may win a card's window.

The defect these pin: ``add_plan`` reads ``resource_planner`` to decide whether
anything overlaps and then inserts, with nothing between the two. Sent
sequentially the second request correctly gets a 409; sent together, every
request reads a table that does not yet hold the others' rows, every one
concludes "free", and every one inserts. Measured on a live install: 4 simultaneous
``POST /item/reservables-planner`` -> 4x200, four live plans on one card for the
same profile, ``sum(units) == 4`` against ``total_units == 1``.

So these tests have to be genuinely concurrent -- a sequential loop passes
against the broken code and proves nothing. The harness runs N real threads
released together by a ``threading.Barrier``, against an in-memory stand-in for
``resource_planner`` that models RethinkDB honestly for this purpose:

* each query takes a consistent snapshot under its own lock (per-query
  atomicity, which RethinkDB does give), but
* nothing is atomic ACROSS queries (which RethinkDB does not give), and
* every query costs a few ms, like a real round trip -- this is what makes the
  interleaving reproducible rather than a coin flip.

The mutual exclusion under test is real: ``resource_lock`` takes an actual redis
lease, so what these assert is the production mechanism, not a stub of it.
"""

import threading
import time
import uuid
from datetime import datetime, timedelta

import pytest
import pytz
import redis as redis_lib
from isardvdi_common.connections.redis_urls import rq_url
from isardvdi_common.lib.bookings import reservables_planner as mod

# One card, one profile, one unit: the capacity the four racing plans
# blew through. Card ids are minted per test so a leftover lease from
# a previous run can never be what makes one of these pass.
PROFILE_ID = "NVIDIA-L40S-8Q"
TOTAL_UNITS = 1
THREADS = 8

# Simulated per-query round trip. Wide enough that all THREADS finish their
# overlap reads before any of them inserts (the real-world interleaving), small
# enough that the whole test stays well under a second.
QUERY_LATENCY_S = 0.01


def _redis_or_fail():
    """The lease is real, so the test needs the same redis the helper uses."""
    conn = redis_lib.from_url(rq_url(), socket_connect_timeout=5, socket_timeout=5)
    try:
        conn.ping()
    except Exception as error:
        from isardvdi_common.redis_test_gate import redis_required

        redis_required(f"no Redis for the planner concurrency test: {error}")
    return conn


# --- a minimal, honest stand-in for the resource_planner table ---------------


class _Pred:
    """A ReQL predicate reduced to a python callable over one row."""

    def __init__(self, fn):
        self.fn = fn

    def __and__(self, other):
        return _Pred(lambda row: self.fn(row) and other.fn(row))

    def __or__(self, other):
        return _Pred(lambda row: self.fn(row) or other.fn(row))


class _Field:
    def __init__(self, key):
        self.key = key

    def during(self, lo, hi):
        # RethinkDB's during() is left-closed / right-open by default.
        return _Pred(lambda row: lo <= row[self.key] < hi)

    def __le__(self, value):
        return _Pred(lambda row: row[self.key] <= value)

    def __ge__(self, value):
        return _Pred(lambda row: row[self.key] >= value)

    def __lt__(self, value):
        return _Pred(lambda row: row[self.key] < value)

    def __gt__(self, value):
        return _Pred(lambda row: row[self.key] > value)


class _RowExpr:
    def __getitem__(self, key):
        return _Field(key)


class _Table:
    """In-memory rows + the atomicity RethinkDB actually offers.

    ``insert`` and each ``run`` are individually serialised (per-query
    atomicity); two queries issued by the same caller are NOT (no transaction).
    """

    _INDEXES = {
        "item_id": lambda row: row["item_id"],
        "type-item-subitem": lambda row: [
            row["item_type"],
            row["item_id"],
            row["subitem_id"],
        ],
        "item-subitem": lambda row: [row["item_id"], row["subitem_id"]],
    }

    def __init__(self):
        self.rows = []
        self._lock = threading.Lock()

    def insert(self, row):
        with self._lock:
            self.rows.append(dict(row))
        return True

    def snapshot(self):
        with self._lock:
            return [dict(row) for row in self.rows]


class _Query:
    def __init__(self, table, preds=None):
        self._table = table
        self._preds = list(preds or [])

    def get_all(self, key, index=None):
        keyfn = _Table._INDEXES[index]
        return _Query(self._table, self._preds + [_Pred(lambda row: keyfn(row) == key)])

    def filter(self, pred):
        return _Query(self._table, self._preds + [pred])

    def run(self, _conn):
        # Order matters: the answer reflects the table AS OF when the query ran,
        # and only then does the round trip cost time. Sleeping first instead
        # would sample the table after the wire delay, which quietly hands every
        # reader the winner's row and hides the very race under test.
        rows = self._table.snapshot()
        for pred in self._preds:
            rows = [row for row in rows if pred.fn(row)]
        time.sleep(QUERY_LATENCY_S)
        return rows


class _R:
    """Stand-in for the module's ``r``."""

    def __init__(self, table):
        self._table = table
        self.row = _RowExpr()

    def table(self, name):
        assert name == "resource_planner", f"unexpected table {name}"
        return _Query(self._table)


class _Reservables:
    """The behaviour flags ``ResourceItemsGpus`` reports for a GPU card."""

    def __init__(self, item_can_overlap=False, subitem_can_overlap=True):
        self._item_can_overlap = item_can_overlap
        self._subitem_can_overlap = subitem_can_overlap

    def get_subitem_units(self, _item_type, _item_id, _subitem):
        return TOTAL_UNITS

    def planning_item_can_overlap(self, _item_type, _item_id):
        return self._item_can_overlap

    def planning_subitem_can_overlap(self, _item_type, _item_id, _subitem):
        return self._subitem_can_overlap

    def planning_subitem_join_before(self, _item_type, _item_id, _subitem):
        return False

    def planning_subitem_join_after(self, _item_type, _item_id, _subitem):
        return False

    def planning_schedule_subitem(self, _item_type, _item_id, _subitem):
        return True


class _Ctx:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


@pytest.fixture
def planner(monkeypatch):
    """``add_plan`` wired to the in-memory table, everything else stubbed."""
    _redis_or_fail()
    table = _Table()

    monkeypatch.setattr(mod, "r", _R(table))
    monkeypatch.setattr(
        mod.ReservablesPlannerProccess, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.ReservablesPlannerProccess),
        "_rdb_connection",
        property(lambda self: None),
    )
    monkeypatch.setattr(mod.ReservablesPlannerProccess, "reservables", _Reservables())
    # The insert goes through the model, which owns its own rethink handle.
    monkeypatch.setattr(
        mod.ResourcePlanner,
        "insert_plan",
        classmethod(lambda cls, plan: table.insert(plan)),
    )
    # Registering the profile-switch job is not what is under test.
    monkeypatch.setattr(
        mod.ReservablesPlannerProccess,
        "new_subitem_schedule",
        classmethod(lambda cls, plan: None),
    )
    return table


def _plan_data(card_id):
    start = datetime.now(pytz.utc) + timedelta(days=1)
    return {
        "item_type": "gpus",
        "item_id": card_id,
        "subitem_id": PROFILE_ID,
        "start": start,
        "end": start + timedelta(hours=4),
    }


def _payload(user_id="local-default-admin-admin"):
    return {"user_id": user_id, "role_id": "admin", "category_id": "default"}


def _race(count, data_for):
    """Fire ``count`` add_plan calls that all cross the check->insert window."""
    barrier = threading.Barrier(count)
    outcomes = [None] * count

    def worker(index):
        data = data_for(index)
        barrier.wait()
        try:
            outcomes[index] = (
                "ok",
                mod.ReservablesPlannerProccess.add_plan(_payload(), data),
            )
        except Exception as error:  # Error (409/429) or anything unexpected
            outcomes[index] = ("error", error)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=60)
    assert not any(thread.is_alive() for thread in threads), "a worker deadlocked"
    return outcomes


class TestConcurrentPlansOnOneCard:
    def test_only_one_of_n_simultaneous_identical_plans_is_created(self, planner):
        """N at once must behave like N in a row: one 200, N-1 conflicts.

        Fails on the unguarded code with N plans inserted (measured: 8/8).
        """
        card_id = f"hyp-test-{uuid.uuid4()}"
        outcomes = _race(THREADS, lambda _i: _plan_data(card_id))

        created = [o for o in outcomes if o[0] == "ok"]
        failed = [o for o in outcomes if o[0] == "error"]

        assert len(planner.rows) == 1, (
            f"{len(planner.rows)} plans landed on one card for the same window; "
            "the check-then-insert was not atomic"
        )
        assert len(created) == 1
        assert len(failed) == THREADS - 1
        # Every loser must fail for the RIGHT reason: the winner's row is there,
        # so it is an overlap conflict (409), not a lock timeout or a crash.
        for _tag, error in failed:
            assert getattr(error, "status_code", None) == 409, error

    def test_summed_units_never_exceed_total_units(self, planner):
        """The invariant the four racing plans broke: sum(units) <= capacity."""
        card_id = f"hyp-test-{uuid.uuid4()}"
        _race(THREADS, lambda _i: _plan_data(card_id))

        booked = sum(row["units"] for row in planner.rows)
        assert (
            booked <= TOTAL_UNITS
        ), f"{booked} units planned against a total_units of {TOTAL_UNITS}"

    def test_different_profiles_on_one_card_still_cannot_overlap(self, planner):
        """The card-wide rule is profile-agnostic, so the lease must be too.

        A per-card+profile lease would let 8Q and 4Q race into the same window on
        one card -- exactly the overlap ``check_plan_item_id_overlapped`` exists
        to reject ("we can't overlap in gpu").
        """
        card_id = f"hyp-test-{uuid.uuid4()}"

        def data_for(index):
            data = _plan_data(card_id)
            data["subitem_id"] = f"NVIDIA-L40S-{index}Q"
            return data

        outcomes = _race(THREADS, data_for)

        assert len(planner.rows) == 1, (
            f"{len(planner.rows)} different profiles were planned into the same "
            "window on one physical card"
        )
        assert len([o for o in outcomes if o[0] == "ok"]) == 1


class TestPlannerIsNotSerialisedGlobally:
    def test_plans_on_different_cards_all_succeed(self, planner):
        """The section is per card: N cards planned at once give N plans.

        Guards the other half of the fix -- a global lock would also make this
        pass one plan at a time, turning a rare corruption into a permanent
        queue. Here every card must win.
        """
        outcomes = _race(
            THREADS, lambda index: _plan_data(f"hyp-test-{uuid.uuid4()}-{index}")
        )

        assert len(planner.rows) == THREADS
        assert len([o for o in outcomes if o[0] == "ok"]) == THREADS

    def test_different_cards_do_not_wait_for_each_other(self, planner):
        """...and they do it CONCURRENTLY, not one after another.

        N sections that each cost ~3 queries would take ~N x 3 x latency if they
        queued behind one lease; running in parallel they take ~3 x latency. The
        bound below sits between the two, so a lock that is too coarse trips it.
        """
        started = time.monotonic()
        _race(THREADS, lambda index: _plan_data(f"hyp-test-{uuid.uuid4()}-{index}"))
        elapsed = time.monotonic() - started

        serial_estimate = THREADS * 3 * QUERY_LATENCY_S
        assert elapsed < serial_estimate, (
            f"{elapsed:.3f}s for {THREADS} independent cards is serial-shaped "
            f"(a queued run would need ~{serial_estimate:.3f}s); the critical "
            "section is too coarse"
        )


class TestLeaseIsReleased:
    def test_a_conflicting_plan_does_not_leak_its_lease(self, planner):
        """A section that raises must still release, or the card wedges for 30s.

        The first plan wins; the second raises 409 inside the section. If the
        release were not in a ``finally``, the third call would then block on the
        dead lease and time out (429) instead of getting its honest 409.
        """
        card_id = f"hyp-test-{uuid.uuid4()}"
        assert mod.ReservablesPlannerProccess.add_plan(_payload(), _plan_data(card_id))

        for _attempt in range(2):
            with pytest.raises(Exception) as raised:
                mod.ReservablesPlannerProccess.add_plan(_payload(), _plan_data(card_id))
            assert getattr(raised.value, "status_code", None) == 409, raised.value

        assert len(planner.rows) == 1
