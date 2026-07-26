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
import time
from datetime import datetime, timezone

import pytest
from isardvdi_common.lib import governor_counters as gcnt
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

    def __getattr__(self, name):
        def _queue(*args, **kwargs):
            self._ops.append((name, args, kwargs))
            return self

        return _queue

    def execute(self):
        return [
            getattr(self._redis, name)(*args, **kwargs)
            for (name, args, kwargs) in self._ops
        ]


class _FakeRedis:
    def __init__(self):
        self.sets = {}
        self.hashes = {}
        self.lists = {}  # lane -> queued count
        self.strings = {}
        self.zsets = {}
        self.ttls = {}
        self.fail = False

    def _boom(self):
        if self.fail:
            raise RuntimeError("redis down")

    def smembers(self, key):
        self._boom()
        return set(self.sets.get(key, ()))

    def hgetall(self, key):
        self._boom()
        return dict(self.hashes.get(key, {}))

    def llen(self, key):
        self._boom()
        return self.lists.get(key, 0)

    def hincrby(self, key, field, amount=1):
        self._boom()
        h = self.hashes.setdefault(key, {})
        h[field] = str(int(h.get(field, 0)) + amount)
        return int(h[field])

    def hset(self, key, mapping=None):
        self._boom()
        self.hashes.setdefault(key, {}).update(
            {k: str(v) for k, v in (mapping or {}).items()}
        )
        return len(mapping or {})

    def incr(self, key):
        self._boom()
        self.strings[key] = str(int(self.strings.get(key, 0)) + 1)
        return int(self.strings[key])

    def expire(self, key, ttl):
        self._boom()
        self.ttls[key] = ttl
        return True

    def ttl(self, key):
        self._boom()
        return self.ttls.get(key, -2)

    def zadd(self, key, mapping):
        self._boom()
        self.zsets.setdefault(key, {}).update(mapping)
        return len(mapping)

    def zscore(self, key, member):
        self._boom()
        return self.zsets.get(key, {}).get(member)

    def zrem(self, key, member):
        self._boom()
        return 1 if self.zsets.get(key, {}).pop(member, None) is not None else 0

    @staticmethod
    def _score_bound(raw):
        """Parse a redis score-bound token: a number, "-inf"/"+inf", or a
        "(<score>" exclusive form. Returns (value, inclusive)."""
        if isinstance(raw, (int, float)):
            return float(raw), True
        s = str(raw)
        if s in ("-inf", "+inf"):
            return float(s.replace("inf", "inf")), True
        if s.startswith("("):
            return float(s[1:]), False
        return float(s), True

    def _in_range(self, score, min_score, max_score):
        lo, lo_incl = self._score_bound(min_score)
        hi, hi_incl = self._score_bound(max_score)
        above_lo = score > lo or (lo_incl and score == lo)
        below_hi = score < hi or (hi_incl and score == hi)
        return above_lo and below_hi

    def zcount(self, key, min_score, max_score):
        self._boom()
        return sum(
            1
            for score in self.zsets.get(key, {}).values()
            if self._in_range(score, min_score, max_score)
        )

    def zremrangebyscore(self, key, min_score, max_score):
        self._boom()
        zset = self.zsets.get(key, {})
        stale = [m for m, s in zset.items() if self._in_range(s, min_score, max_score)]
        for member in stale:
            del zset[member]
        return len(stale)

    def mget(self, keys):
        self._boom()
        return [self.strings.get(k) for k in keys]

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


# --- lane_shed_decision: a NO-CONSUMER lane is rejected for EVERY tier -------
# (fail-fast: a task nothing can drain must not be enqueued — it would strand
# forever. The backlog/hard-cap rules below stay foreground-only.)


def test_reject_governed_tier_stranded_no_consumer():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)  # serves DEF, not "ghost"
    # a governed (background) lane on a pool with NO live worker must be refused
    decision, ctx = qc.lane_shed_decision(r, "storage.ghost.background")
    assert decision == "reject"
    assert ctx["reason"] == "no_consumer"
    assert ctx["stranded"] is True and ctx["has_consumer"] is False


def test_reject_ctx_carries_category_for_scoped_notification():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    # per-category lane on an unserved pool -> reject, and the ctx names the
    # category so the caller can scope the "pool unavailable" signal to it.
    decision, ctx = qc.lane_shed_decision(r, "storage.ghost.cat-abc.maintenance")
    assert decision == "reject" and ctx["reason"] == "no_consumer"
    assert ctx["pool"] == "ghost"
    assert ctx["category"] == "cat-abc"


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


def test_enforce_shed_rejects_stranded_even_without_opt_in():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)  # serves DEF, not ghost
    # No shed=True: the no-consumer refusal is MANDATORY (fail-fast), so a
    # produce to a dead pool is rejected even for a governed tier.
    kwargs = {"queue": "storage.ghost.maintenance"}
    try:
        qc.enforce_shed(r, kwargs)
        raised = None
    except Exception as exc:
        raised = exc
    assert getattr(raised, "status_code", None) == 429
    assert getattr(raised, "error", {}).get("description_code") == (
        "storage_no_consumer_retry_later"
    )


def test_enforce_shed_noop_when_consumer_present_but_backed_up():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    r.lists[f"rq:queue:storage.{DEF}.background"] = 999
    # a governed lane WITH a live consumer but backed up: accepted (accumulates),
    # only the truly-stranded (no-consumer) case is refused.
    kwargs = {"queue": f"storage.{DEF}.background", "shed": True}
    qc.enforce_shed(r, kwargs)
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


# --- shed observability -----------------------------------------------------
#
# A shed is a decision nobody but the rejected user sees. These pin that every
# 429 leaves a durable, dimensioned trace, and that the trace can never become
# a second failure mode of the gate itself.


def test_no_consumer_rejection_records_a_durable_counter():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    with pytest.raises(Exception):
        qc.check_no_consumer(r, "storage.ghost.standard")
    doc = gcnt.read_shed(r)
    assert doc["total"] == 1
    assert doc["recent"] == 1
    assert doc["by_reason"] == {"no_consumer": 1}
    assert doc["by_tier"] == {"standard": 1}
    assert doc["last_pool"] == "ghost"
    assert doc["last_tier"] == "standard"


def test_overload_rejection_is_counted_under_its_own_reason():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    r.lists[f"rq:queue:storage.{DEF}.interactive"] = 10_000
    with pytest.raises(Exception):
        qc.check_shed(r, f"storage.{DEF}.interactive")
    doc = gcnt.read_shed(r)
    assert doc["by_reason"] == {"overloaded": 1}
    assert doc["by_tier"] == {"interactive": 1}


def test_accepted_enqueue_records_no_shed():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    qc.enforce_shed(r, {"queue": f"storage.{DEF}.standard", "shed": True})
    assert gcnt.read_shed(r) == gcnt.empty_counters()


def test_shed_storm_accumulates_across_pools_and_tiers():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    for tier in ("interactive", "standard", "bulk"):
        for pool in ("ghost-a", "ghost-b"):
            with pytest.raises(Exception):
                qc.check_no_consumer(r, f"storage.{pool}.{tier}")
    doc = gcnt.read_shed(r)
    assert doc["total"] == 6
    assert doc["recent"] == 6
    assert doc["by_tier"] == {"interactive": 2, "standard": 2, "bulk": 2}


# --- coverage-index publish primitive ---------------------------------------


def test_publish_lane_adds_member_and_ttl():
    r = _FakeRedis()
    qc.publish_lane(r, "p1", "interactive", "w1", 100.0, 15)
    assert r.zscore(qc.cov_key("p1", "interactive"), "w1") == 100.0
    assert 0 < r.ttl(qc.cov_key("p1", "interactive")) <= 15


def test_unpublish_worker_removes_member():
    r = _FakeRedis()
    qc.publish_lane(r, "p1", "interactive", "w1", 100.0, 15)
    qc.unpublish_worker(r, "p1", "interactive", "w1")
    assert r.zscore(qc.cov_key("p1", "interactive"), "w1") is None


def test_pool_live_workers_counts_fresh():
    r = _FakeRedis()
    qc.publish_lane(r, "p1", "interactive", "w1", 1000.0, 15)
    qc.publish_lane(r, "p1", "interactive", "w2", 1000.0, 15)
    assert qc.pool_live_workers(r, "p1", "interactive", now=1000.0, ttl=15) == 2


def test_pool_live_workers_excludes_stale():
    r = _FakeRedis()
    qc.publish_lane(r, "p1", "interactive", "w_old", 900.0, 15)
    qc.publish_lane(r, "p1", "interactive", "w_new", 1000.0, 15)
    assert qc.pool_live_workers(r, "p1", "interactive", now=1000.0, ttl=15) == 1


def test_pool_live_workers_zero_when_empty():
    r = _FakeRedis()
    assert qc.pool_live_workers(r, "p1", "interactive", now=1000.0) == 0


# --- lane_shed_decision: LIVE index is the primary has-consumer signal ------


class _IndexBoomRedis(_FakeRedis):
    """Fails only on the live-index read, proving the try/except around
    lane_shed_decision covers pool_live_workers too, not just served_coverage."""

    def zremrangebyscore(self, key, min_score, max_score):
        raise RuntimeError("index down")


def test_decision_ok_when_index_live():
    r = _FakeRedis()
    # lane_shed_decision reads the index with no explicit now/ttl, so publish
    # against the real wall clock it will use.
    qc.publish_lane(r, "p1", "interactive", "w1", time.time(), qc.COV_TTL_S)
    decision, ctx = qc.lane_shed_decision(r, "storage.p1.interactive")
    assert decision == "ok"
    assert ctx["has_consumer"] is True


def test_decision_reject_no_consumer_index_empty_fleet_up():
    r = _FakeRedis()
    # index empty for p1, but p2 is served (legacy fallback) -> fleet is up
    _governed_worker(r, "w1", "p2")
    decision, ctx = qc.lane_shed_decision(r, "storage.p1.standard")
    assert decision == "reject"
    assert ctx["reason"] == "no_consumer"


def test_decision_fail_open_no_coverage_data_when_fleet_invisible():
    r = _FakeRedis()  # index empty AND no rq:workers at all
    decision, ctx = qc.lane_shed_decision(r, "storage.p1.interactive")
    assert decision == "ok"
    assert ctx["reason"] == "no_coverage_data"


def test_decision_fail_open_on_redis_error():
    r = _IndexBoomRedis()
    _governed_worker(r, "w1", "p1")
    decision, ctx = qc.lane_shed_decision(r, "storage.p1.interactive")
    assert decision == "ok"
    assert ctx["reason"] == "coverage_error"


def test_decision_reject_overloaded_foreground_over_cap():
    r = _FakeRedis()
    qc.publish_lane(r, "p1", "interactive", "w1", time.time(), qc.COV_TTL_S)
    r.lists["rq:queue:storage.p1.interactive"] = qc.hard_cap("interactive") + 5
    decision, ctx = qc.lane_shed_decision(r, "storage.p1.interactive")
    assert decision == "reject"
    assert ctx["reason"] == "overloaded"
    assert ctx["hard_cap"] == qc.hard_cap("interactive")


def test_decision_ok_governed_over_backlog():
    r = _FakeRedis()
    qc.publish_lane(r, "p1", "bulk", "w1", time.time(), qc.COV_TTL_S)
    r.lists["rq:queue:storage.p1.bulk"] = 10_000
    decision, ctx = qc.lane_shed_decision(r, "storage.p1.bulk")
    assert decision != "reject"
    assert ctx.get("reason") != "overloaded"


def test_counter_failure_never_swallows_the_429():
    """The counter is observability, not a gate: a redis blip between the shed
    decision and the INCR must still leave the caller with the typed 429."""
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    _, ctx = qc.lane_shed_decision(r, "storage.ghost.standard")
    r.fail = True
    with pytest.raises(Exception) as excinfo:
        qc._raise_lane_429(r, ctx)
    assert getattr(excinfo.value, "status_code", None) == 429
