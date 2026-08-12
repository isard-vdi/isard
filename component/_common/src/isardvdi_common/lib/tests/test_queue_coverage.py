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
from isardvdi_common.lib import category_pools
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

    def set(self, key, value):
        self._boom()
        self.strings[key] = value
        return True

    def get(self, key):
        self._boom()
        return self.strings.get(key)

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


def test_empty_fleet_rejects_because_it_is_knowledge():
    # redis answered every read and reported no worker at all: that is a fact
    # about the fleet, not an inability to see it.
    decision, ctx = qc.lane_shed_decision(_FakeRedis(), f"storage.{DEF}.interactive")
    assert decision == "reject"
    assert ctx["reason"] == "no_consumer"


def test_an_unreadable_index_rejects_rather_than_admitting_blind():
    """Was ``test_fail_open_on_redis_error``, asserting the opposite. Admitting
    on a read failure is the guard yielding exactly where it is needed: the
    caller now gets the same 429 a consumerless lane gives. Genuine emptiness
    that redis DID answer keeps its own paths (fleet gap, no_consumer)."""
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    r.fail = True
    decision, ctx = qc.lane_shed_decision(r, f"storage.{DEF}.interactive")
    assert decision == "reject"
    assert ctx["reason"] == "coverage_unreadable"


def test_non_storage_queue_is_ok():
    decision, ctx = qc.lane_shed_decision(_FakeRedis(), "notifier")
    assert decision == "ok"
    assert ctx["reason"] == "non_storage_queue"


# --- enforce_shed (the create_task gate) -----------------------------------


def test_enforce_shed_pops_legacy_shed_key_even_when_it_rejects():
    # ``shed`` is a deprecated/legacy kwarg now (overload is mandatory, not
    # opt-in): it is popped regardless of its value AND of the outcome.
    r = _FakeRedis()  # no workers at all -> no_consumer
    kwargs = {"queue": "storage.ghost.standard", "shed": False, "task": "resize"}
    with pytest.raises(Exception):
        qc.enforce_shed(r, kwargs)
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


def test_enforce_shed_rejects_stranded_governed_tier():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)  # serves DEF, not ghost
    # No shed key at all: the no-consumer refusal is MANDATORY (fail-fast), so a
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


# --- enforce_shed: the foreground overload gate is now mandatory (Task 7) --


def test_enforce_shed_blocks_overloaded_foreground_without_flag():
    r = _FakeRedis()
    qc.publish_lane(r, "p1", "interactive", "w1", time.time(), qc.COV_TTL_S)
    r.lists["rq:queue:storage.p1.interactive"] = qc.hard_cap("interactive") + 5
    kwargs = {"queue": "storage.p1.interactive"}  # NO "shed" key
    try:
        qc.enforce_shed(r, kwargs)
        raised = None
    except Exception as exc:
        raised = exc
    assert raised is not None
    assert getattr(raised, "status_code", None) == 429
    assert getattr(raised, "error", {}).get("description_code") == (
        "storage_overloaded_retry_later"
    )


def test_enforce_shed_ignores_overload_on_governed():
    r = _FakeRedis()
    qc.publish_lane(r, "p1", "bulk", "w1", time.time(), qc.COV_TTL_S)
    r.lists["rq:queue:storage.p1.bulk"] = 10_000
    qc.enforce_shed(r, {"queue": "storage.p1.bulk"})  # must not raise


def test_enforce_shed_still_blocks_no_consumer():
    r = _FakeRedis()
    _governed_worker(r, "w1", "p2")  # keeps the fleet visible; p1 stays stranded
    try:
        qc.enforce_shed(r, {"queue": "storage.p1.interactive"})
        raised = None
    except Exception as exc:
        raised = exc
    assert raised is not None
    assert getattr(raised, "status_code", None) == 429
    assert getattr(raised, "error", {}).get("description_code") == (
        "storage_no_consumer_retry_later"
    )


def test_enforce_shed_pops_shed_kwarg():
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    kwargs = {"queue": f"storage.{DEF}.interactive", "shed": True}
    qc.enforce_shed(r, kwargs)  # healthy lane -> no raise, same as without shed
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


def test_decision_rejects_when_index_and_registry_are_both_empty():
    r = _FakeRedis()  # index empty AND no rq:workers at all, both readable
    decision, ctx = qc.lane_shed_decision(r, "storage.p1.interactive")
    assert decision == "reject"
    assert ctx["reason"] == "no_consumer"


def test_decision_rejects_when_the_index_cannot_be_read():
    """Was ``test_decision_fail_open_on_redis_error``. Same reason as above:
    the index blowing up is ignorance, not a verdict about the fleet."""
    r = _IndexBoomRedis()
    _governed_worker(r, "w1", "p1")
    decision, ctx = qc.lane_shed_decision(r, "storage.p1.interactive")
    assert decision == "reject"
    assert ctx["reason"] == "coverage_unreadable"


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


def test_health_available_when_pool_live(monkeypatch):
    monkeypatch.setattr(category_pools, "category_pool_ids", lambda cid: ["p1"])
    r = _FakeRedis()
    qc.publish_lane(r, "p1", "interactive", "w1", time.time(), qc.COV_TTL_S)
    health = qc.category_storage_health(r, "cat-a")
    assert health["available"] is True
    interactive = next(p for p in health["pools"] if p["tier"] == "interactive")
    assert interactive["pool"] == "p1"
    assert interactive["no_consumer"] is False
    assert interactive["overloaded"] is False
    assert interactive["degraded"] is False


def test_health_no_consumer_when_pool_empty(monkeypatch):
    monkeypatch.setattr(category_pools, "category_pool_ids", lambda cid: ["p1"])
    r = _FakeRedis()
    # index empty for p1, but p2 served (legacy fallback) -> fleet is up, so
    # p1's absence is a genuine no-consumer, not a fail-open blip.
    _governed_worker(r, "w1", "p2")
    health = qc.category_storage_health(r, "cat-a")
    interactive = next(p for p in health["pools"] if p["tier"] == "interactive")
    assert interactive["no_consumer"] is True
    assert health["available"] is False


def test_health_overloaded_when_foreground_over_cap(monkeypatch):
    monkeypatch.setattr(category_pools, "category_pool_ids", lambda cid: ["p1"])
    r = _FakeRedis()
    qc.publish_lane(r, "p1", "interactive", "w1", time.time(), qc.COV_TTL_S)
    r.lists["rq:queue:storage.p1.interactive"] = qc.hard_cap("interactive") + 5
    health = qc.category_storage_health(r, "cat-a")
    interactive = next(p for p in health["pools"] if p["tier"] == "interactive")
    assert interactive["overloaded"] is True
    assert health["available"] is False


def test_health_degraded_on_redis_error(monkeypatch):
    monkeypatch.setattr(category_pools, "category_pool_ids", lambda cid: ["p1"])
    r = _FakeRedis()
    _governed_worker(r, "w1", "p1")
    r.fail = True
    health = qc.category_storage_health(r, "cat-a")  # must not raise
    interactive = next(p for p in health["pools"] if p["tier"] == "interactive")
    assert interactive["degraded"] is True
    assert health["available"] is False


# --- a dead fleet is knowledge; an unreadable one is ignorance --------------
#
# The whole storage worker set being stopped used to read as "no coverage data"
# and fail OPEN, so creation kept succeeding and every task piled up on a lane
# nothing could drain. The two states must get opposite biases, and the code can
# tell them apart: ``pool_live_workers`` and ``served_coverage`` both RAISE on a
# redis error and only return empty when redis answered.


class _RegistryBoomRedis(_FakeRedis):
    """The live index reads fine (and is empty) but the RQ worker registry is
    unreadable: we cannot SEE the fleet, so the gate must stay open."""

    def smembers(self, key):
        raise RuntimeError("registry unreadable")


def test_whole_fleet_stopped_rejects_every_tier():
    r = _FakeRedis()  # readable, and it says there is no worker anywhere
    for tier in ALL_TIERS:
        decision, ctx = qc.lane_shed_decision(r, f"storage.{DEF}.{tier}")
        assert (decision, ctx["reason"]) == ("reject", "no_consumer"), tier
        assert ctx["has_consumer"] is False and ctx["stranded"] is True


def test_unreadable_redis_refuses_instead_of_admitting_blind():
    """Renamed from ``test_unreadable_redis_still_fails_open``. Redis being
    unreachable is the absence of an answer, and the gate no longer reads it as
    a good one."""
    r = _FakeRedis()
    r.fail = True
    decision, ctx = qc.lane_shed_decision(r, f"storage.{DEF}.interactive")
    assert decision == "reject"
    assert ctx["reason"] == "coverage_unreadable"


def test_unreadable_worker_registry_refuses_too():
    """The registry is one of the reads the coverage answer is built from, so
    it cannot be read is the same ignorance as the index being unreadable."""
    decision, ctx = qc.lane_shed_decision(
        _RegistryBoomRedis(), f"storage.{DEF}.standard"
    )
    assert decision == "reject"
    assert ctx["reason"] == "coverage_unreadable"


def test_stale_registry_entry_is_not_a_live_consumer():
    r = _FakeRedis()
    # a worker that died uncleanly: still a member of rq:workers, heartbeat long
    # expired and no governor hash -> the fleet is visible AND down
    r.sets.setdefault("rq:workers", set()).add("rq:worker:dead")
    r.hashes["rq:worker:dead"] = {
        "queues": f"storage.{DEF}.interactive",
        "last_heartbeat": "2020-01-01T00:00:00.000000Z",
    }
    decision, ctx = qc.lane_shed_decision(r, f"storage.{DEF}.interactive")
    assert decision == "reject"
    assert ctx["reason"] == "no_consumer"


def test_worker_for_another_pool_leaves_both_pools_unchanged():
    r = _FakeRedis()
    _governed_worker(r, "w1", "p-served")
    served, served_ctx = qc.lane_shed_decision(r, "storage.p-served.standard")
    assert served == "ok" and served_ctx["has_consumer"] is True
    dead, dead_ctx = qc.lane_shed_decision(r, "storage.p-dead.standard")
    assert dead == "reject" and dead_ctx["reason"] == "no_consumer"


def test_opaque_pool_immunity_holds_when_it_is_the_whole_fleet():
    r = _FakeRedis()
    # the only live worker is opaque and was born on one lane: it might serve
    # overflow we cannot see, so no lane of ITS pool may be declared stranded
    _opaque_worker(r, "res1", DEF, tiers=("interactive",))
    for tier in ALL_TIERS:
        decision, ctx = qc.lane_shed_decision(r, f"storage.{DEF}.{tier}")
        assert decision == "ok" and ctx["stranded"] is False, tier
    # ...and that immunity does not leak to a pool it was not born on
    decision, ctx = qc.lane_shed_decision(r, "storage.other.background")
    assert decision == "reject" and ctx["reason"] == "no_consumer"


def test_enforce_shed_rejects_with_429_when_whole_fleet_is_down():
    r = _FakeRedis()
    try:
        qc.enforce_shed(r, {"queue": f"storage.{DEF}.standard"})
        raised = None
    except Exception as exc:
        raised = exc
    assert raised is not None
    assert getattr(raised, "status_code", None) == 429
    assert getattr(raised, "error", {}).get("description_code") == (
        "storage_no_consumer_retry_later"
    )


def test_fleet_down_shed_is_counted_under_no_consumer():
    r = _FakeRedis()
    with pytest.raises(Exception):
        qc.check_no_consumer(r, f"storage.{DEF}.background")
    doc = gcnt.read_shed(r)
    assert doc["by_reason"] == {"no_consumer": 1}
    assert doc["by_tier"] == {"background": 1}


def test_health_says_no_consumer_not_degraded_when_fleet_down(monkeypatch):
    monkeypatch.setattr(category_pools, "category_pool_ids", lambda cid: ["p1"])
    health = qc.category_storage_health(_FakeRedis(), "cat-a")
    interactive = next(p for p in health["pools"] if p["tier"] == "interactive")
    assert interactive["no_consumer"] is True
    assert interactive["degraded"] is False
    assert health["available"] is False


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


# --- the fleet gap: a restart is not the same as a stopped fleet -------------
#
# A clean worker shutdown unpublishes its lanes right away rather than letting
# the TTL expire, so a rolling restart makes the index read empty for a few
# seconds. Treating that instant as "the fleet is gone" turns the normal upgrade
# path into a fleet-wide refusal, which is worse than the fail-open it replaced.


def test_a_brief_gap_after_the_fleet_was_seen_still_admits():
    r = _FakeRedis()
    qc.note_fleet_seen(r, now=1000.0)
    decision, ctx = qc.lane_shed_decision(
        r, f"storage.{DEF}.standard", now=1000.0 + qc.FLEET_GONE_GRACE_S / 2
    )
    assert decision == "ok"
    assert ctx["reason"] == "fleet_gap"


def test_a_gap_longer_than_the_grace_sheds():
    r = _FakeRedis()
    qc.note_fleet_seen(r, now=1000.0)
    decision, ctx = qc.lane_shed_decision(
        r, f"storage.{DEF}.standard", now=1000.0 + qc.FLEET_GONE_GRACE_S + 1
    )
    assert decision == "reject"
    assert ctx["reason"] == "no_consumer"


def test_a_fleet_never_seen_sheds_rather_than_queueing_into_the_void():
    """No sighting at all is not a restart gap: nothing has ever heartbeated, so
    refusing is accurate, and it self-heals as soon as a worker publishes."""
    r = _FakeRedis()
    decision, ctx = qc.lane_shed_decision(r, f"storage.{DEF}.standard", now=1000.0)
    assert decision == "reject"
    assert ctx["reason"] == "no_consumer"


def test_seeing_a_live_worker_records_the_sighting():
    r = _FakeRedis()
    qc.publish_lane(r, DEF, "standard", "w1", now=500.0, ttl=qc.COV_TTL_S)
    qc.lane_shed_decision(r, f"storage.{DEF}.standard", now=500.0)
    assert qc.fleet_last_seen(r) == 500.0


# --- exact boundaries of the reject/warn/grace thresholds (off-by-one guards) --


def test_reject_at_exactly_the_hard_cap():
    """A foreground lane AT its hard cap is already refused: the cap is the first
    backlog that must not be exceeded, so the test is ``>=``, not ``>``."""
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    r.lists[f"rq:queue:storage.{DEF}.interactive"] = qc.hard_cap("interactive")
    decision, ctx = qc.lane_shed_decision(r, f"storage.{DEF}.interactive")
    assert decision == "reject"
    assert ctx["reason"] == "overloaded"


def test_warn_at_exactly_the_warn_backlog():
    """A lane AT its warn threshold is already backed up: the boundary belongs to
    ``warn``, not to ``ok``."""
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    assert qc.warn_backlog("interactive") < qc.hard_cap(
        "interactive"
    )  # else it'd reject
    r.lists[f"rq:queue:storage.{DEF}.interactive"] = qc.warn_backlog("interactive")
    decision, ctx = qc.lane_shed_decision(r, f"storage.{DEF}.interactive")
    assert decision == "warn"


def test_grace_window_includes_its_exact_edge():
    """A lane whose fleet was seen EXACTLY ``FLEET_GONE_GRACE_S`` ago is still
    inside the grace window and admits: the edge belongs to the window (``<=``),
    so a rolling restart at the boundary is not misread as a dead fleet."""
    r = _FakeRedis()  # empty fleet -> would be no_consumer without the grace
    seen = 1000.0
    qc.note_fleet_seen(r, seen)
    decision, ctx = qc.lane_shed_decision(
        r, f"storage.{DEF}.interactive", now=seen + qc.FLEET_GONE_GRACE_S
    )
    assert decision == "ok"
    assert ctx["reason"] == "fleet_gap"
