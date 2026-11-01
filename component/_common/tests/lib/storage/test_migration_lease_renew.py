# SPDX-License-Identifier: AGPL-3.0-or-later

"""The advance lease must not lapse during a full pass, and renewing it must not
abort a big migration. A pass over a large ledger (an occurrence re-scan) can run
minutes, past ADVANCE_LOCK_TTL; the runner renews the lease AS it plans and drains
(rate-limited), so the lease stays alive and the pass completes instead of aborting
every time planning outlasts the TTL."""

from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.lib.storage import migration_run as mr
from redis.exceptions import LockError

from .test_migration_drive_events import _scripted_saga
from .test_migration_recurring_drive import (
    NOW,
    WINDOW,
    _FakeRedis,
    _item,
    _Mig,
    _runner,
)


class _CountingLease:
    def __init__(self, raise_at=None):
        self.reacquires = 0
        self._raise_at = raise_at

    def reacquire(self):
        self.reacquires += 1
        if self._raise_at is not None and self.reacquires >= self._raise_at:
            raise LockError("lease lost")
        return True


class _Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    def advance(self, dt):
        self.t += dt


class _ExpiringLease:
    """A real-ish lease: reacquire() succeeds only while the TTL has not elapsed
    on the fake clock since the last renewal, else it raises as redis-py would."""

    def __init__(self, clock, ttl):
        self._clock = clock
        self._ttl = ttl
        self._valid_since = clock()
        self.reacquires = 0

    def reacquire(self):
        self.reacquires += 1
        if self._clock() - self._valid_since > self._ttl:
            raise LockError("lease expired")
        self._valid_since = self._clock()
        return True


def _three_pending_trees():
    return [
        _item("a", "pending", tree="a"),
        _item("b", "pending", tree="b"),
        _item("c", "pending", tree="c"),
    ]


def _pass_runner(monkeypatch, lease):
    items = _three_pending_trees()
    m = _Mig("running", {"parallelism": 3})
    m.record_activity = lambda delta=None: None
    jf = _scripted_saga(monkeypatch, set())
    r = _runner(monkeypatch, items, m, now=NOW, job_status_fn=jf)
    redis = _FakeRedis()
    monkeypatch.setattr(mr, "shared_client", lambda *a, **k: redis)
    monkeypatch.setattr(mr, "rq_url", lambda: "redis://x")

    def _start(self, it):
        self._set(it, state="moving", move_task_id=f"t-{it['storage_id']}")

    r._ACTIONS = {"start": _start, "finish": lambda self, it: None}
    r._lease = lease
    return r, items


def test_full_pass_renews_the_lease_during_the_pass(monkeypatch):
    lease = _CountingLease()
    r, items = _pass_runner(monkeypatch, lease)

    r.tick()

    assert [it["state"] for it in items] == ["moving", "moving", "moving"]
    assert lease.reacquires >= 1


def test_full_pass_aborts_before_writing_when_the_lease_is_lost(monkeypatch):
    lease = _CountingLease(raise_at=1)
    r, items = _pass_runner(monkeypatch, lease)

    raised = None
    try:
        r.tick()
    except Exception as exc:  # noqa: BLE001 — asserting the type below
        raised = exc

    assert raised is not None and type(raised).__name__ == "LeaseLost"
    assert [it["state"] for it in items] == ["pending", "pending", "pending"]


def test_lease_renew_is_rate_limited(monkeypatch):
    # Thousands of per-item heartbeats must collapse to a handful of redis calls.
    clock = _Clock()
    monkeypatch.setattr(mr, "time", clock)
    lease = _CountingLease()
    r, _items = _pass_runner(monkeypatch, lease)
    r._last_renew = clock()

    for _ in range(100):
        r._renew_lease()
    assert lease.reacquires == 0  # all within one interval

    clock.advance(mr.LEASE_RENEW_INTERVAL + 1)
    for _ in range(100):
        r._renew_lease()
    assert lease.reacquires == 1  # one renewal after the interval elapsed


def test_both_rescans_pass_a_heartbeat_into_the_planner(monkeypatch):
    seen = {}

    def _capture(mid, roots, pool, *, heartbeat=None, **k):
        seen["hb"] = heartbeat
        return ([], {})

    m = _Mig("scheduled", {"recurring": True, "window": WINDOW})
    r = _runner(monkeypatch, [], m, now=NOW, planned=[])
    r._snapshot = None
    monkeypatch.setattr(mig, "build_plan_for_roots", _capture)  # after _runner's stub

    r._rescan_insert_new()
    assert callable(seen.get("hb")) and seen["hb"] == r._renew_lease

    seen.clear()
    r._rearm_for_occurrence("2026-07-01")
    assert callable(seen.get("hb")) and seen["hb"] == r._renew_lease


def test_a_pass_whose_planning_outlasts_the_ttl_keeps_the_lease(monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(mr, "time", clock)
    monkeypatch.setattr(mr, "LEASE_RENEW_INTERVAL", 10)
    ttl = 90
    items = [_item("r", "failed", occurrence_failures=0)]
    m = _Mig(
        "scheduled", {"recurring": True, "window": WINDOW, "rescan_cadence": "edge"}
    )
    m.last_occurrence = "2026-06-30"
    m.record_activity = lambda delta=None: None
    r = _runner(monkeypatch, items, m, now=NOW, planned=[_item("r", "pending")])
    r._incremental = False
    r._snapshot = None
    lease = _ExpiringLease(clock, ttl)
    r._lease = lease
    r._last_renew = clock()

    def _slow_plan(mid, roots, pool, *, heartbeat=None, **k):
        for _ in range(5):  # 5 x 30s = 150s > 90s TTL
            clock.advance(30)
            if heartbeat:
                heartbeat()
        return ([_item("r", "pending")], {})

    monkeypatch.setattr(mig, "build_plan_for_roots", _slow_plan)

    assert r._maybe_rescan_occurrence() is True  # completes, no LeaseLost
    assert lease.reacquires >= 1
    assert items[0]["state"] != "failed"  # the failed disk was re-armed
