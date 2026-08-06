#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit coverage for governor_counters: the durable shed / defer event counters.

Covers the monotonic totals, the bounded per-dimension breakdown, the rolling
per-minute window (what makes a single sample show a storm), the last-event
context, and the fail-open/never-raise contract on both the write and read side.
"""

from isardvdi_common.lib import governor_counters as gcnt


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
    def __init__(self, fail=False):
        self.hashes = {}
        self.strings = {}
        self.expires = {}
        self.fail = fail

    def _boom(self):
        if self.fail:
            raise RuntimeError("redis down")

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

    def hgetall(self, key):
        self._boom()
        return dict(self.hashes.get(key, {}))

    def incr(self, key):
        self._boom()
        self.strings[key] = str(int(self.strings.get(key, 0)) + 1)
        return int(self.strings[key])

    def expire(self, key, ttl):
        self._boom()
        self.expires[key] = ttl
        return True

    def mget(self, keys):
        self._boom()
        return [self.strings.get(k) for k in keys]

    def pipeline(self):
        return _Pipe(self)


T0 = 1_800_000_000.0  # a stable, minute-aligned-ish epoch for the window maths


# --- shed -------------------------------------------------------------------


def test_record_shed_increments_total_reason_and_tier():
    r = _FakeRedis()
    gcnt.record_shed(r, "no_consumer", pool="p1", tier="interactive", now=T0)
    gcnt.record_shed(r, "overloaded", pool="p1", tier="interactive", now=T0)
    gcnt.record_shed(r, "overloaded", pool="p2", tier="standard", now=T0)
    doc = gcnt.read_shed(r, now=T0)
    assert doc["total"] == 3
    assert doc["by_reason"] == {"no_consumer": 1, "overloaded": 2}
    assert doc["by_tier"] == {"interactive": 2, "standard": 1}


def test_record_shed_keeps_last_event_context():
    r = _FakeRedis()
    gcnt.record_shed(r, "no_consumer", pool="p1", tier="bulk", now=T0)
    doc = gcnt.read_shed(r, now=T0 + 7.0)
    assert doc["last_reason"] == "no_consumer"
    assert doc["last_pool"] == "p1"
    assert doc["last_tier"] == "bulk"
    assert doc["last_seconds_ago"] == 7.0


def test_shed_recent_window_only_counts_the_window():
    r = _FakeRedis()
    gcnt.record_shed(r, "overloaded", pool="p1", tier="standard", now=T0)
    assert gcnt.read_shed(r, now=T0)["recent"] == 1
    # one full window later the bucket has aged out of the summed range
    stale = T0 + (gcnt.WINDOW_MINUTES + 1) * 60
    doc = gcnt.read_shed(r, now=stale)
    assert doc["recent"] == 0
    assert doc["total"] == 1  # the monotonic total never resets
    assert doc["window_minutes"] == gcnt.WINDOW_MINUTES


def test_shed_window_buckets_expire():
    r = _FakeRedis()
    gcnt.record_shed(r, "overloaded", pool="p1", tier="standard", now=T0)
    assert r.expires  # every bucket key carries a TTL, so nothing accumulates
    assert all(ttl > gcnt.WINDOW_MINUTES * 60 for ttl in r.expires.values())


# --- defer ------------------------------------------------------------------


def test_record_defer_counts_reasons_and_last_worker():
    r = _FakeRedis()
    gcnt.record_defer(r, "psi", worker="w1", now=T0)
    gcnt.record_defer(r, "at_cap", worker="w2", now=T0)
    gcnt.record_defer(r, "psi", worker="w2", now=T0)
    doc = gcnt.read_defer(r, now=T0)
    assert doc["total"] == 3
    assert doc["by_reason"] == {"psi": 2, "at_cap": 1}
    assert doc["recent"] == 3
    assert doc["last_worker"] == "w2"
    assert doc["last_reason"] == "psi"


def test_shed_and_defer_counters_are_independent():
    r = _FakeRedis()
    gcnt.record_shed(r, "no_consumer", pool="p1", tier="interactive", now=T0)
    gcnt.record_defer(r, "psi", worker="w1", now=T0)
    assert gcnt.read_shed(r, now=T0)["total"] == 1
    assert gcnt.read_defer(r, now=T0)["total"] == 1
    assert gcnt.read_shed(r, now=T0)["last_worker"] is None


# --- bounded cardinality ----------------------------------------------------


def test_high_cardinality_dimensions_never_become_counter_fields():
    """pool ids and worker names are unbounded over an install's lifetime; only
    the closed tier set gets its own field, or the hash would grow forever."""
    r = _FakeRedis()
    for i in range(50):
        gcnt.record_shed(r, "overloaded", pool=f"pool{i}", tier="standard", now=T0)
        gcnt.record_defer(r, "psi", worker=f"worker{i}", now=T0)
    shed_fields = set(r.hashes[gcnt.totals_key(gcnt.SHED)])
    defer_fields = set(r.hashes[gcnt.totals_key(gcnt.DEFER)])
    assert not any(f.startswith("pool:") for f in shed_fields)
    assert not any(f.startswith("worker:") for f in defer_fields)
    assert len(shed_fields) < 10 and len(defer_fields) < 10


# --- fail-open --------------------------------------------------------------


def test_record_never_raises_when_redis_is_down():
    r = _FakeRedis(fail=True)
    gcnt.record_shed(r, "no_consumer", pool="p1", tier="interactive", now=T0)
    gcnt.record_defer(r, "psi", worker="w1", now=T0)


def test_read_fails_open_to_a_zeroed_document():
    r = _FakeRedis(fail=True)
    doc = gcnt.read_shed(r, now=T0)
    assert doc == gcnt.empty_counters()
    assert doc["total"] == 0
    assert doc["recent"] == 0
    assert doc["last_ts"] is None
    assert doc["last_seconds_ago"] is None


def test_empty_counters_is_the_never_recorded_shape():
    r = _FakeRedis()
    assert gcnt.read_shed(r, now=T0) == gcnt.empty_counters()
