#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guards of the storage lane GC; the real Lua runs in testing/integration/redis."""

import pytest
from isardvdi_common.lib import governed_worker as gw
from isardvdi_common.lib import queue_lane_gc as gc

GRACE = gc.LANE_GC_GRACE_SECONDS
T0 = 1_000_000.0


class _Pipe:
    def __init__(self, parent):
        self.parent = parent
        self.ops = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def __getattr__(self, name):
        def _queue(*args, **kwargs):
            self.ops.append((name, args, kwargs))
            return self

        return _queue

    def execute(self):
        return [getattr(self.parent, n)(*a, **k) for n, a, k in self.ops]


class FakeRedis:
    """Byte replies like redis-py; ``eval`` mirrors the two Lua scripts."""

    def __init__(self):
        self.sets, self.lists, self.zsets, self.hashes, self.strings = (
            {},
            {},
            {},
            {},
            {},
        )
        self.before_eval = None
        self.after_eval = None

    @staticmethod
    def _b(v):
        return v if isinstance(v, bytes) else str(v).encode()

    @staticmethod
    def _s(v):
        return v.decode() if isinstance(v, bytes) else str(v)

    # sets
    def sadd(self, key, *vals):
        s = self.sets.setdefault(key, set())
        before = len(s)
        s.update(self._s(v) for v in vals)
        return len(s) - before

    def srem(self, key, *vals):
        s = self.sets.get(key, set())
        n = sum(1 for v in vals if self._s(v) in s)
        s.difference_update(self._s(v) for v in vals)
        return n

    def smembers(self, key):
        return {self._b(v) for v in self.sets.get(key, set())}

    def sismember(self, key, val):
        return int(self._s(val) in self.sets.get(key, set()))

    # lists
    def rpush(self, key, *vals):
        self.lists.setdefault(key, []).extend(self._s(v) for v in vals)
        return len(self.lists[key])

    def llen(self, key):
        return len(self.lists.get(key, []))

    # zsets
    def zadd(self, key, mapping):
        self.zsets.setdefault(key, {}).update(
            {self._s(k): float(v) for k, v in mapping.items()}
        )

    def zcard(self, key):
        return len(self.zsets.get(key, {}))

    def zrem(self, key, *vals):
        z = self.zsets.get(key, {})
        return sum(1 for v in vals if z.pop(self._s(v), None) is not None)

    def zrange(self, key, start, end):
        items = sorted(self.zsets.get(key, {}).items(), key=lambda kv: kv[1])
        items = items[start:] if end == -1 else items[start : end + 1]
        return [self._b(k) for k, _ in items]

    def zremrangebyscore(self, key, lo, hi):
        z = self.zsets.get(key, {})
        lo = float("-inf") if lo == "-inf" else float(lo)
        gone = [k for k, v in z.items() if lo <= v <= float(hi)]
        for k in gone:
            del z[k]
        return len(gone)

    # hashes
    def hset(self, key, field, value):
        self.hashes.setdefault(key, {})[self._s(field)] = self._s(value)

    def hdel(self, key, *fields):
        h = self.hashes.get(key, {})
        return sum(1 for f in fields if h.pop(self._s(f), None) is not None)

    def hgetall(self, key):
        return {self._b(k): self._b(v) for k, v in self.hashes.get(key, {}).items()}

    # strings / keys
    def set(self, key, value, nx=False, ex=None):
        if nx and key in self.strings:
            return None
        self.strings[key] = value
        return True

    def delete(self, *keys):
        for k in keys:
            for store in (self.sets, self.lists, self.zsets, self.hashes, self.strings):
                store.pop(k, None)

    def exists(self, *keys):
        stores = (self.sets, self.lists, self.zsets, self.hashes, self.strings)
        return sum(1 for k in keys if any(k in s and s[k] for s in stores))

    def pipeline(self):
        return _Pipe(self)

    def flushdb(self):
        for store in (self.sets, self.lists, self.zsets, self.hashes, self.strings):
            store.clear()

    # scripts
    def eval(self, script, numkeys, *args):
        keys, argv = list(args[:numkeys]), [self._s(a) for a in args[numkeys:]]
        if self.before_eval:
            self.before_eval(self, keys, argv)
        if script == gc._REMOVE_IDLE_LANE_LUA:
            out = self._remove(keys, argv)
        elif script == gc._RESTORE_LANE_LUA:
            out = self._restore(keys, argv)
        else:
            raise AssertionError("unexpected script")
        if self.after_eval:
            self.after_eval(self, keys, argv)
        return out

    def _busy(self, keys):
        return self.llen(keys[1]) > 0 or any(self.zcard(k) > 0 for k in keys[2:6])

    def _remove(self, keys, argv):
        idle = not self._busy(keys) and not any(
            self.exists(w) for w in self.sets.get(keys[6], set())
        )
        self.hdel(keys[7], argv[0])
        if not idle:
            return 0
        removed = self.srem(keys[0], argv[0])
        if removed:
            self.zadd(keys[8], {argv[0]: float(argv[1])})
        return removed

    def _restore(self, keys, argv):
        if self.sismember(keys[0], argv[0]):
            self.zrem(keys[6], argv[0])
            return 0
        if self._busy(keys):
            self.sadd(keys[0], argv[0])
            self.zrem(keys[6], argv[0])
            return 1
        return 0


@pytest.fixture
def r():
    return FakeRedis()


def lane(name):
    return f"rq:queue:{name}"


def registered(r):
    return {m.decode() if isinstance(m, bytes) else m for m in r.smembers("rq:queues")}


def run(r, now):
    """One pass, ignoring the fleet-wide rate limit (that has its own test)."""
    r.delete(gc.LANE_GC_LOCK_KEY)
    return gc.collect_empty_lanes(r, now=now)


def idle_for_grace(r):
    """Two passes: the first starts the idle streak, the second is past it."""
    run(r, T0)
    return run(r, T0 + GRACE + 1)


EMPTY = "storage.p1.cat1.reclaim"


# --- the lane that should go ------------------------------------------------


def test_an_idle_storage_lane_is_unregistered_after_the_grace_period(r):
    r.sadd("rq:queues", lane(EMPTY))

    summary = idle_for_grace(r)

    assert lane(EMPTY) not in registered(r)
    assert summary["removed"] == 1


def test_an_idle_lane_inside_the_grace_period_stays(r):
    r.sadd("rq:queues", lane(EMPTY))

    run(r, T0)
    summary = run(r, T0 + GRACE - 1)

    assert lane(EMPTY) in registered(r)
    assert summary["removed"] == 0 and summary["waiting"] == 1


def test_flat_and_cross_pool_lanes_are_collected_too(r):
    """Every storage lane shape, not only the per-category one: a flat lane of
    a pool with no worker left, and a cross-pool move lane."""
    for name in ("storage.gone.reclaim", "storage.a:b.bulk"):
        r.sadd("rq:queues", lane(name))

    idle_for_grace(r)

    assert registered(r) == set()


# --- the guards ----------------------------------------------------------------


def test_a_queued_job_keeps_the_lane(r):
    r.sadd("rq:queues", lane(EMPTY))
    r.rpush(lane(EMPTY), "job1")

    idle_for_grace(r)

    assert lane(EMPTY) in registered(r)


@pytest.mark.parametrize(
    "registry", ["rq:wip", "rq:deferred", "rq:scheduled", "rq:failed"]
)
def test_a_job_in_any_registry_keeps_the_lane(r, registry):
    """An empty list is not an idle lane: the job may be running (and need the
    started-registry rescue), waiting on a dependency, waiting for its retry,
    or failed and waiting for an operator."""
    r.sadd("rq:queues", lane(EMPTY))
    r.zadd(f"{registry}:{EMPTY}", {"job1": 1})

    idle_for_grace(r)

    assert lane(EMPTY) in registered(r)


def test_a_live_worker_on_the_lane_keeps_it(r):
    r.sadd("rq:queues", lane(EMPTY))
    r.sadd(f"rq:workers:{EMPTY}", "rq:worker:w1")
    r.hset("rq:worker:w1", "state", "idle")

    idle_for_grace(r)

    assert lane(EMPTY) in registered(r)


def test_a_dead_worker_registration_does_not_keep_the_lane(r):
    """``rq:workers:<lane>`` outlives a killed worker; its hash does not."""
    r.sadd("rq:queues", lane(EMPTY))
    r.sadd(f"rq:workers:{EMPTY}", "rq:worker:gone")

    idle_for_grace(r)

    assert lane(EMPTY) not in registered(r)


@pytest.mark.parametrize(
    "name",
    [
        "default",  # a non-storage RQ queue
        "notifier",
        "storage",  # prefix only
        "storage.a.b.c.d",  # does not parse as a storage lane
        "storagex.p.reclaim",
    ],
)
def test_a_non_storage_queue_is_never_touched(r, name):
    r.sadd("rq:queues", lane(name))

    idle_for_grace(r)

    assert lane(name) in registered(r)


def test_work_in_between_restarts_the_idle_streak(r):
    r.sadd("rq:queues", lane(EMPTY))
    run(r, T0)  # idle
    r.rpush(lane(EMPTY), "job1")
    run(r, T0 + 10)  # busy -> streak reset
    r.delete(lane(EMPTY))
    run(r, T0 + 20)  # idle again, a new streak starts here

    run(r, T0 + GRACE + 1)  # past the FIRST streak, not the second

    assert lane(EMPTY) in registered(r)
    run(r, T0 + 20 + GRACE + 1)
    assert lane(EMPTY) not in registered(r)


# --- races with an enqueue ----------------------------------------------------


def test_the_script_rechecks_a_job_pushed_after_the_read(r):
    """A job lands between the pipelined read and the script."""
    r.sadd("rq:queues", lane(EMPTY))
    run(r, T0)

    def _enqueue(fake, keys, argv):
        if keys[0] == "rq:queues" and keys[1] == lane(EMPTY):
            fake.rpush(lane(EMPTY), "late")

    r.before_eval = _enqueue
    summary = run(r, T0 + GRACE + 1)

    assert lane(EMPTY) in registered(r)
    assert summary["removed"] == 0


def test_a_job_pushed_right_after_the_removal_is_put_back_in_the_same_pass(r):
    """RQ's enqueue SADDs and pushes in two round trips; a removal can land between."""
    r.sadd("rq:queues", lane(EMPTY))
    run(r, T0)

    def _push_after_removal(fake, keys, argv):
        if len(keys) == 9 and argv[0] == lane(EMPTY):  # the removal script
            fake.after_eval = None
            fake.rpush(lane(EMPTY), "late")

    r.after_eval = _push_after_removal
    summary = run(r, T0 + GRACE + 1)

    assert summary["removed"] == 1 and summary["restored"] == 1
    assert lane(EMPTY) in registered(r)


def test_a_removed_lane_that_got_work_without_registering_is_put_back(r):
    r.sadd("rq:queues", lane(EMPTY))
    idle_for_grace(r)
    assert lane(EMPTY) not in registered(r)
    r.rpush(lane(EMPTY), "late")  # pushed, never SADDed

    summary = run(r, T0 + GRACE + 600)

    assert lane(EMPTY) in registered(r)
    assert summary["restored"] == 1


def test_an_enqueue_re_registers_a_removed_lane_and_is_not_undone(r):
    r.sadd("rq:queues", lane(EMPTY))
    idle_for_grace(r)
    r.sadd("rq:queues", lane(EMPTY))  # what RQ's enqueue does
    r.rpush(lane(EMPTY), "job1")

    summary = run(r, T0 + GRACE + 600)

    assert lane(EMPTY) in registered(r)
    assert summary["restored"] == 0
    assert r.zcard(gc.LANE_GC_REMOVED_KEY) == 0


def test_removals_are_forgotten_after_the_watch_window(r):
    r.sadd("rq:queues", lane(EMPTY))
    idle_for_grace(r)
    assert r.zcard(gc.LANE_GC_REMOVED_KEY) == 1

    run(r, T0 + GRACE + 1 + gc.LANE_GC_WATCH_SECONDS + 1)

    assert r.zcard(gc.LANE_GC_REMOVED_KEY) == 0


# --- the pass itself ------------------------------------------------------------


def test_the_pass_is_rate_limited_fleet_wide(r):
    r.sadd("rq:queues", lane(EMPTY))
    r.delete(gc.LANE_GC_LOCK_KEY)

    first = gc.collect_empty_lanes(r, now=T0)
    second = gc.collect_empty_lanes(r, now=T0 + GRACE + 1)

    assert first["skipped"] is False
    assert second == {"skipped": True}
    assert lane(EMPTY) in registered(r)


def test_a_redis_error_never_raises_and_changes_nothing():
    class _Broken(FakeRedis):
        def smembers(self, key):
            raise ConnectionError("redis went away")

    r = _Broken()
    r.sets["rq:queues"] = {lane(EMPTY)}

    summary = gc.collect_empty_lanes(r, now=T0)

    assert summary.get("error") is True
    assert r.sets["rq:queues"] == {lane(EMPTY)}


def test_idle_streaks_of_unregistered_lanes_are_dropped(r):
    r.sadd("rq:queues", lane(EMPTY))
    run(r, T0)
    r.srem("rq:queues", lane(EMPTY))  # gone some other way

    run(r, T0 + 10)

    assert r.hgetall(gc.LANE_GC_IDLE_SINCE_KEY) == {}


def test_six_hundred_idle_lanes_go_and_the_busy_ones_stay(r):
    idle = [f"storage.p{i % 7}.c{i}.reclaim" for i in range(600)]
    busy = [f"storage.p{i}.busy.bulk" for i in range(5)]
    for name in idle + busy:
        r.sadd("rq:queues", lane(name))
    for name in busy:
        r.rpush(lane(name), "job")
    r.sadd("rq:queues", lane("default"))

    summary = idle_for_grace(r)

    assert summary["removed"] == 600
    assert registered(r) == {lane(n) for n in busy} | {lane("default")}


# --- wiring -----------------------------------------------------------------


def test_the_worker_maintenance_runs_the_pass(monkeypatch):
    """The governed worker's registry maintenance is where the pass runs, so
    every storage worker can trigger it and the lock keeps it to one."""
    calls = []
    monkeypatch.setattr(gc, "collect_empty_lanes", lambda conn: calls.append(conn))
    monkeypatch.setattr(gw.Worker, "clean_registries", lambda self: None)
    w = object.__new__(gw.GovernedWorker)
    w.connection = object()
    w.multitenancy = False

    w.clean_registries()

    assert calls == [w.connection]
