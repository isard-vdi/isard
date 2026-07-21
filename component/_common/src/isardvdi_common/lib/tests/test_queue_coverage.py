#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit coverage for queue_coverage: served_coverage + lane_shed_decision.

Exercises the reject/warn/ok matrix, the foreground-only reject rule, the
per-pool opacity that suppresses false stranding, and the fail-open paths.
"""

import json
from datetime import datetime, timezone

from isardvdi_common.lib import queue_coverage as qc

DEF = "00000000-0000-0000-0000-000000000000"
ALL_TIERS = (
    "interactive",
    "standard",
    "template",
    "bulk",
    "maintenance",
    "reclaim",
    "background",
)


def _fresh_heartbeat():
    try:
        from rq.utils import utcformat

        return utcformat(datetime.now(timezone.utc))
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")


class _Pipe:
    def __init__(self, redis):
        self._redis = redis
        self._ops = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def hgetall(self, key):
        self._ops.append(key)
        return self

    def execute(self):
        return [self._redis.hgetall(key) for key in self._ops]


class _FakeRedis:
    def __init__(self):
        self.sets = {}
        self.hashes = {}
        self.lists = {}  # lane -> queued count
        self.fail = False

    def smembers(self, key):
        if self.fail:
            raise RuntimeError("redis down")
        return set(self.sets.get(key, ()))

    def hgetall(self, key):
        return dict(self.hashes.get(key, {}))

    def llen(self, key):
        if self.fail:
            raise RuntimeError("redis down")
        return self.lists.get(key, 0)

    def pipeline(self):
        return _Pipe(self)


def _governed_worker(r, name, pool, tiers=ALL_TIERS):
    """A governor worker: publishes served_lanes -> known/exact coverage."""
    lanes = [f"storage.{pool}.{t}" for t in tiers]
    r.sets.setdefault("rq:workers", set()).add(f"rq:worker:{name}")
    r.hashes[f"rq:worker:{name}"] = {"queues": ",".join(lanes)}
    r.hashes[f"governor:worker:{name}"] = {
        "served_lanes": json.dumps(lanes),
        "kind": "elastic",
    }


def _opaque_worker(r, name, pool, tiers=("interactive", "standard")):
    """A plain reserved/std-lane worker: no governor hash -> opaque pool."""
    lanes = [f"storage.{pool}.{t}" for t in tiers]
    r.sets.setdefault("rq:workers", set()).add(f"rq:worker:{name}")
    r.hashes[f"rq:worker:{name}"] = {
        "queues": ",".join(lanes),
        "last_heartbeat": _fresh_heartbeat(),
    }


# --- served_coverage --------------------------------------------------------


def test_served_coverage_governed_worker_is_known():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    covered, opaque = qc.served_coverage(r)
    assert (DEF, "interactive") in covered
    assert (DEF, "background") in covered
    assert opaque == set()


def test_served_coverage_opaque_worker_marks_pool_opaque():
    r = _FakeRedis()
    _opaque_worker(r, "res1", DEF)
    covered, opaque = qc.served_coverage(r)
    # its birth lanes still count as covered, but the pool is opaque
    assert (DEF, "interactive") in covered
    assert opaque == {DEF}


def test_served_coverage_empty_fleet():
    covered, opaque = qc.served_coverage(_FakeRedis())
    assert not covered and opaque == set()


def test_served_coverage_counts_workers_per_lane():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    _governed_worker(r, "w2", DEF)
    covered, _opaque = qc.served_coverage(r)
    assert covered[(DEF, "interactive")] == 2  # both workers serve the lane


# --- lane_shed_decision: reject -------------------------------------------


def test_reject_foreground_stranded_no_consumer():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)  # serves DEF, not "ghost"
    decision, ctx = qc.lane_shed_decision(r, "storage.ghost.standard")
    assert decision == "reject"
    assert ctx["reason"] == "no_consumer"
    assert ctx["stranded"] is True and ctx["has_consumer"] is False


def test_reject_foreground_over_hard_cap():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    r.lists[f"rq:queue:storage.{DEF}.interactive"] = qc.hard_cap("interactive") + 5
    decision, ctx = qc.lane_shed_decision(r, f"storage.{DEF}.interactive")
    assert decision == "reject"
    assert ctx["reason"] == "overloaded"
    assert ctx["has_consumer"] is True  # a consumer exists, but it is swamped


# --- lane_shed_decision: never reject a governed tier ----------------------


def test_governed_tier_never_rejected_even_when_stranded():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    # a stranded background lane: no consumer, but background never blocks
    decision, ctx = qc.lane_shed_decision(r, "storage.ghost.background")
    assert decision == "ok"
    assert ctx["stranded"] is True  # informed, but accepted (accumulates)


def test_governed_tier_over_backlog_warns_not_rejects():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    r.lists[f"rq:queue:storage.{DEF}.maintenance"] = qc.warn_backlog("maintenance") + 1
    decision, ctx = qc.lane_shed_decision(r, f"storage.{DEF}.maintenance")
    assert decision == "warn"


# --- lane_shed_decision: warn + ok -----------------------------------------


def test_warn_foreground_backed_up_below_hard_cap():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    r.lists[f"rq:queue:storage.{DEF}.interactive"] = qc.warn_backlog("interactive") + 1
    decision, ctx = qc.lane_shed_decision(r, f"storage.{DEF}.interactive")
    assert decision == "warn"
    assert ctx["reason"] == "backlog"


def test_ok_healthy_lane():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    decision, ctx = qc.lane_shed_decision(r, f"storage.{DEF}.interactive")
    assert decision == "ok"
    assert ctx["has_consumer"] is True and ctx["stranded"] is False


# --- opacity suppresses false stranding ------------------------------------


def test_opaque_pool_suppresses_stranding_for_uncovered_tier():
    r = _FakeRedis()
    # an opaque worker in DEF serving only interactive/standard; a maintenance
    # task in DEF is not directly covered, but the opaque worker might serve it
    _opaque_worker(r, "res1", DEF, tiers=("interactive",))
    decision, ctx = qc.lane_shed_decision(r, f"storage.{DEF}.standard")
    # standard is foreground + uncovered, but DEF is opaque -> not stranded
    assert ctx["stranded"] is False
    assert decision in ("ok", "warn")


# --- fail-open --------------------------------------------------------------


def test_fail_open_on_empty_fleet():
    decision, ctx = qc.lane_shed_decision(_FakeRedis(), f"storage.{DEF}.interactive")
    assert decision == "ok"
    assert ctx["reason"] == "no_coverage_data"


def test_fail_open_on_redis_error():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    r.fail = True
    decision, ctx = qc.lane_shed_decision(r, f"storage.{DEF}.interactive")
    assert decision == "ok"
    assert ctx["reason"] == "coverage_error"


def test_non_storage_queue_is_ok():
    decision, ctx = qc.lane_shed_decision(_FakeRedis(), "notifier")
    assert decision == "ok"
    assert ctx["reason"] == "non_storage_queue"


# --- enforce_shed (the create_task gate) -----------------------------------


def test_enforce_shed_pops_flag_and_is_noop_when_not_opted_in():
    r = _FakeRedis()  # no workers -> would be no_coverage_data anyway
    kwargs = {"queue": "storage.ghost.standard", "shed": False, "task": "resize"}
    qc.enforce_shed(r, kwargs)  # must not raise
    assert "shed" not in kwargs  # popped so it never reaches Task(**kwargs)


def test_enforce_shed_noop_on_healthy_lane():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    kwargs = {"queue": f"storage.{DEF}.interactive", "shed": True}
    qc.enforce_shed(r, kwargs)  # consumer present -> no raise
    assert "shed" not in kwargs


def test_enforce_shed_rejects_stranded_foreground_with_429():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)  # serves DEF, not ghost
    kwargs = {"queue": "storage.ghost.standard", "shed": True}
    try:
        qc.enforce_shed(r, kwargs)
        raised = None
    except Exception as exc:  # error_factory Error / ErrorBase
        raised = exc
    assert raised is not None
    assert getattr(raised, "status_code", None) == 429
    assert getattr(raised, "error", {}).get("description_code") == (
        "storage_no_consumer_retry_later"
    )


def test_enforce_shed_never_rejects_governed_tier():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    kwargs = {"queue": "storage.ghost.background", "shed": True}
    qc.enforce_shed(r, kwargs)  # background is never rejected
    assert "shed" not in kwargs


def test_check_shed_raises_on_stranded_and_noop_on_healthy():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    qc.check_shed(r, f"storage.{DEF}.standard")  # healthy -> no raise
    try:
        qc.check_shed(r, "storage.ghost.standard")
        raised = None
    except Exception as exc:
        raised = exc
    assert getattr(raised, "status_code", None) == 429
