#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit coverage for queue_coverage.lane_has_consumer: the non-raising posture.

The gate is mandatory on every producer; the VERB is not. A producer answering a
user raises a typed 429 (``check_no_consumer``); a producer running with nobody
to answer must DECLINE instead, because an exception there is caught, logged as
a traceback and the work is lost just as quietly as if it had been enqueued into
the void. These pin that the second posture reaches the same verdict as the
first, counts the same shed, and never raises.

Reuses the fake redis and the worker-publishing helpers of test_queue_coverage:
this is the same coverage index, read the same way.
"""

import json
import time
from datetime import datetime, timezone

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


def _plain_worker(r, name, pool, tiers=("interactive", "standard")):
    """A plain reserved/std-lane worker: no governor hash, so its RQ birth
    ``queues`` are exactly what it consumes -> known coverage, pool stays read."""
    lanes = [f"storage.{pool}.{t}" for t in tiers]
    r.sets.setdefault("rq:workers", set()).add(f"rq:worker:{name}")
    r.hashes[f"rq:worker:{name}"] = {
        "queues": ",".join(lanes),
        "last_heartbeat": _fresh_heartbeat(),
    }


def _identity(doc):
    """A shed document minus the wall-clock fields, so two recordings taken a
    few microseconds apart can be compared for being the SAME event."""
    return {k: v for k, v in doc.items() if k not in ("last_ts", "last_seconds_ago")}


# --- the "no" answers -------------------------------------------------------


def test_a_lane_with_no_consumer_is_declined():
    """If this fails, a background producer places work on a pool whose workers
    are all gone: the row is marked done-ish and the task never runs."""
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)  # serves DEF, not "ghost"
    allowed, ctx = qc.lane_has_consumer(r, "storage.ghost.standard")
    assert allowed is False
    assert ctx["reason"] == "no_consumer"
    assert ctx["pool"] == "ghost" and ctx["tier"] == "standard"


def test_an_unreadable_index_is_declined_rather_than_admitted_blind():
    """If this fails, a redis blip turns the mandatory gate OFF for every
    non-raising producer at once — the exact moment work must not be placed."""
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    r.fail = True
    allowed, ctx = qc.lane_has_consumer(r, f"storage.{DEF}.interactive")
    assert allowed is False
    assert ctx["reason"] == "coverage_unreadable"


def test_a_whole_dead_fleet_is_declined_for_a_background_tier_too():
    """If this fails, the tiers nobody watches (background/reclaim) keep being
    fed after the last worker died, and strand silently instead of deferring."""
    r = _FakeRedis()  # nothing published, nothing ever seen
    allowed, ctx = qc.lane_has_consumer(r, f"storage.{DEF}.background")
    assert allowed is False
    assert ctx["reason"] == "no_consumer"


def test_a_worker_on_another_tier_does_not_excuse_the_lane():
    """If this fails, a reserved worker subscribed to one tier vouches for the
    whole pool, and work placed on the tier it does not serve strands forever."""
    r = _FakeRedis()
    _plain_worker(r, "res1", DEF, tiers=("interactive",))
    allowed, ctx = qc.lane_has_consumer(r, f"storage.{DEF}.standard")
    assert allowed is False
    assert ctx["reason"] == "no_consumer"
    assert ctx["stranded"] is True


def test_a_declined_lane_names_its_category_for_a_scoped_notice():
    """If this fails, the operator learns a lane was declined but not WHICH
    category lost its pool, so the outage cannot be scoped or announced."""
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    allowed, ctx = qc.lane_has_consumer(r, "storage.ghost.cat-abc.maintenance")
    assert allowed is False
    assert ctx["pool"] == "ghost"
    assert ctx["category"] == "cat-abc"
    assert ctx["tier"] == "maintenance"


# --- the "yes" answers ------------------------------------------------------


def test_a_non_storage_queue_is_allowed():
    """If this fails, every producer that enqueues onto a non-storage lane
    (notifier and friends) stops dead: they have no pool to be covered."""
    r = _FakeRedis()
    allowed, ctx = qc.lane_has_consumer(r, "notifier")
    assert allowed is True
    assert ctx["reason"] == "non_storage_queue"


def test_a_live_lane_is_allowed():
    """If this fails, a healthy install declines its own work: every deferred
    producer stops placing tasks while the workers sit idle."""
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    allowed, ctx = qc.lane_has_consumer(r, f"storage.{DEF}.standard")
    assert allowed is True
    assert ctx["has_consumer"] is True and ctx["stranded"] is False


def test_a_lane_covered_only_by_the_live_index_is_allowed():
    """If this fails, the heartbeat index is not trusted on its own and a pool
    served exclusively by governed workers reads as dead."""
    r = _FakeRedis()
    now = time.time()
    qc.publish_lane(r, DEF, "bulk", "w1", now, qc.COV_TTL_S)
    allowed, ctx = qc.lane_has_consumer(r, f"storage.{DEF}.bulk")
    assert allowed is True
    assert ctx["has_consumer"] is True


def test_a_rolling_restart_gap_is_allowed():
    """If this fails, every rolling worker upgrade makes each non-raising
    producer decline fleet-wide for the seconds the index is empty."""
    r = _FakeRedis()  # empty index; the fleet WAS seen a moment ago
    qc.note_fleet_seen(r, time.time())
    allowed, ctx = qc.lane_has_consumer(r, f"storage.{DEF}.standard")
    assert allowed is True
    assert ctx["reason"] == "fleet_gap"


def test_a_served_but_swamped_lane_is_still_allowed():
    """If this fails, a backlog is mistaken for an absent pool: work that WILL
    run gets deferred, and a busy install looks like a broken one."""
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    r.lists[f"rq:queue:storage.{DEF}.interactive"] = qc.hard_cap("interactive") + 5
    decision, _ = qc.lane_shed_decision(r, f"storage.{DEF}.interactive")
    assert decision == "reject"  # the 429 gate DOES refuse this one
    allowed, ctx = qc.lane_has_consumer(r, f"storage.{DEF}.interactive")
    assert allowed is True  # ...but somebody can drain it, so placing is right
    assert ctx["has_consumer"] is True


# One counter for both postures: a decline leaves no 429 and no user to notice it,
# so without the shed counter a dead pool would stop looking stranded.


def test_a_decline_increments_the_shed_counter():
    """If this fails, the fleet alarm goes SILENT exactly when a pool dies:
    nothing is enqueued, so nothing is stranded, so nothing is reported."""
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    before = gcnt.read_shed(r)
    assert before == gcnt.empty_counters()

    allowed, _ctx = qc.lane_has_consumer(r, "storage.ghost.standard")
    assert allowed is False

    after = gcnt.read_shed(r)
    assert after["total"] == before["total"] + 1
    assert after["recent"] == before["recent"] + 1
    assert after["by_reason"] == {"no_consumer": 1}
    assert after["by_tier"] == {"standard": 1}
    assert after["last_pool"] == "ghost"
    assert after["last_tier"] == "standard"


def test_a_decline_and_a_429_land_in_the_same_bucket():
    """If this fails, the two postures diverge and the shed dashboards under-
    count by however much of the fleet declines instead of raising."""
    declined = _FakeRedis()
    _governed_worker(declined, "w1", DEF)
    qc.lane_has_consumer(declined, "storage.ghost.standard")

    raised = _FakeRedis()
    _governed_worker(raised, "w1", DEF)
    try:
        qc.check_no_consumer(raised, "storage.ghost.standard")
        blew_up = False
    except Exception:
        blew_up = True
    assert blew_up  # the raising twin still raises on the same lane

    assert _identity(gcnt.read_shed(declined)) == _identity(gcnt.read_shed(raised))


def test_an_allowed_lane_records_no_shed():
    """If this fails, healthy traffic poisons the shed counter and the storm
    signal becomes noise nobody can act on."""
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    allowed, _ctx = qc.lane_has_consumer(r, f"storage.{DEF}.standard")
    assert allowed is True
    assert gcnt.read_shed(r) == gcnt.empty_counters()


def test_a_decline_storm_accumulates_per_pool_and_tier():
    """If this fails, a dead pool registers as one shed no matter how much work
    it refuses, and the rate window can never show the storm."""
    r = _FakeRedis()
    _governed_worker(r, "w1", DEF)
    for tier in ("standard", "bulk"):
        for pool in ("ghost-a", "ghost-b"):
            allowed, _ = qc.lane_has_consumer(r, f"storage.{pool}.{tier}")
            assert allowed is False
    doc = gcnt.read_shed(r)
    assert doc["total"] == 4
    assert doc["recent"] == 4
    assert doc["by_reason"] == {"no_consumer": 4}
    assert doc["by_tier"] == {"standard": 2, "bulk": 2}


# --- the whole point: it must never raise ----------------------------------


def test_it_never_raises_in_any_posture():
    """If this fails, the non-raising twin raises somewhere and its callers --
    background loops that swallow exceptions -- lose the work silently, which
    is the exact failure the declining posture exists to prevent."""
    healthy = _FakeRedis()
    _governed_worker(healthy, "w1", DEF)

    dead = _FakeRedis()
    _governed_worker(dead, "w1", DEF)

    gap = _FakeRedis()
    qc.note_fleet_seen(gap, time.time())

    unreadable = _FakeRedis()
    _governed_worker(unreadable, "w1", DEF)
    unreadable.fail = True

    empty = _FakeRedis()

    cases = [
        (healthy, f"storage.{DEF}.standard", True),
        (dead, "storage.ghost.standard", False),
        (gap, f"storage.{DEF}.standard", True),
        (unreadable, f"storage.{DEF}.standard", False),
        (empty, f"storage.{DEF}.background", False),
        (empty, "notifier", True),
        (empty, "", True),
        (empty, "storage.only-two-parts", True),
    ]
    for conn, queue, expected in cases:
        try:
            allowed, ctx = qc.lane_has_consumer(conn, queue)
        except Exception as exc:  # pragma: no cover - the assertion below reports
            raise AssertionError(
                f"lane_has_consumer raised {exc!r} for queue {queue!r}"
            ) from exc
        assert allowed is expected, f"{queue!r} -> {allowed} (ctx={ctx})"
        assert isinstance(ctx, dict)
