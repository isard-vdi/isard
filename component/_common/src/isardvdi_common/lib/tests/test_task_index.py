# SPDX-License-Identifier: AGPL-3.0-or-later

"""The per-owner task index: a Redis ZSET beside the jobs it names.

``storage.task`` is a pointer from RethinkDB into Redis and the two stores
retain independently, so the row outlives the job it names. Keeping the
reference in the store it points at removes that class of bug, and yields the
*list* rather than only the last one.

Two invariants these tests defend:

* **Pruned by rank, never by clock.** A plain ZADD + EXPIRE does not make a
  dangling member impossible: EXPIRE is per key and every new task on the disk
  refreshes it, so a member outlives its own job by however long the disk stays
  busy. Capping to the newest N and dropping ids whose job is gone on read makes
  it structurally impossible with no clock at all.
* **A task may be indexed under more than one owner.** A convert destination has
  no tasks of its own and resolves through its origin; a parked template row
  names the chain that will unpark it. A single-owner index cannot express
  either.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.lib import task_index
from isardvdi_common.lib.task_index import (
    index_cap,
    index_key,
    index_task,
    owner_task_ids,
)


class _FakeRedis:
    """Just enough real ZSET semantics to test rank pruning and ordering.

    The repo carries no fakeredis, and this needs sorted-set behaviour rather
    than call assertions — a MagicMock cannot tell you that the *oldest*
    members were the ones dropped.
    """

    def __init__(self, listpack_max=128):
        self.z = {}  # key -> {member: score}
        self.h = {}  # key -> hash (only membership matters here)
        self.listpack_max = listpack_max

    def config_get(self, name):
        if self.listpack_max is None:
            raise RuntimeError("config get disabled on this server")
        return {name: str(self.listpack_max)}

    # ── sorted set ────────────────────────────────────────────────────
    def zadd(self, key, mapping):
        self.z.setdefault(key, {}).update(mapping)

    def _sorted(self, key):
        return [m for m, _ in sorted(self.z.get(key, {}).items(), key=lambda kv: kv[1])]

    def zrange(self, key, start, end):
        members = self._sorted(key)
        return [m.encode() for m in members[start : None if end == -1 else end + 1]]

    def zrevrange(self, key, start, end):
        members = list(reversed(self._sorted(key)))
        return [m.encode() for m in members[start : None if end == -1 else end + 1]]

    def zremrangebyrank(self, key, start, end):
        members = self._sorted(key)
        doomed = members[start : None if end == -1 else end + 1]
        for m in doomed:
            self.z[key].pop(m, None)
        return len(doomed)

    def zrem(self, key, *members):
        for m in members:
            self.z.get(key, {}).pop(m, None)

    def zcard(self, key):
        return len(self.z.get(key, {}))

    def zscore(self, key, member):
        return self.z.get(key, {}).get(member)

    # ── generic ───────────────────────────────────────────────────────
    def hset(self, key, field, value):
        self.h.setdefault(key, {})[field] = value

    def exists(self, key):
        return 1 if key in self.h else 0

    def ttl(self, key):
        return -1  # nothing here ever sets one, which is the point

    def keys(self, _pattern):
        return [k.encode() for k in list(self.z) + list(self.h)]

    def pipeline(self, transaction=True):
        return _FakePipeline(self)


class _FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.queued = []

    def __getattr__(self, name):
        def _queue(*args, **kwargs):
            self.queued.append((name, args, kwargs))
            return self

        return _queue

    def execute(self):
        out = []
        for name, args, kwargs in self.queued:
            out.append(getattr(self.redis, name)(*args, **kwargs))
        self.queued = []
        return out


@pytest.fixture(autouse=True)
def _forget_resolved_cap():
    """The cap is resolved once per process; each test resolves it afresh."""
    task_index._cap = None
    yield
    task_index._cap = None


@pytest.fixture
def redis():
    return _FakeRedis()


def _job(job_id, enqueued_at=None, created_at=None):
    job = MagicMock()
    job.id = job_id
    job.enqueued_at = enqueued_at
    job.created_at = created_at
    return job


def _dt(ts):
    from datetime import datetime, timezone

    return datetime.fromtimestamp(ts, tz=timezone.utc)


def _alive(redis, *job_ids):
    for job_id in job_ids:
        redis.hset(f"rq:job:{job_id}", "status", "queued")


class TestKeyShape:
    def test_storage_and_media_have_separate_namespaces(self):
        assert index_key("storage", "d-1") == "storage:d-1:tasks"
        assert index_key("media", "d-1") == "media:d-1:tasks"


class TestIndexWrite:
    def test_a_task_lands_under_its_owner(self, redis):
        index_task(redis, _job("j-1", enqueued_at=_dt(100)), ["d-1"])
        assert redis.zrange("storage:d-1:tasks", 0, -1) == [b"j-1"]
        assert redis.zscore("storage:d-1:tasks", "j-1") == 100

    def test_the_score_falls_back_to_created_at(self, redis):
        """A job built with ``enqueue=False`` has no ``enqueued_at`` until it is
        placed on its queue, but it is already indexable."""
        index_task(redis, _job("j-1", enqueued_at=None, created_at=_dt(50)), ["d-1"])
        assert redis.zscore("storage:d-1:tasks", "j-1") == 50

    def test_the_score_prefers_enqueued_at_over_created_at(self, redis):
        """When BOTH clocks are set they rank differently, and the score must be
        ``enqueued_at`` — when the job reached its queue — not ``created_at``,
        which is only the ``enqueue=False`` fallback. A swapped fallback order
        would rank every normally-enqueued job by its build time instead."""
        index_task(
            redis, _job("j-1", enqueued_at=_dt(100), created_at=_dt(50)), ["d-1"]
        )
        assert redis.zscore("storage:d-1:tasks", "j-1") == 100

    def test_one_task_may_name_several_owners(self, redis):
        index_task(redis, _job("j-1", enqueued_at=_dt(100)), ["d-1", "d-2"])
        assert redis.zrange("storage:d-1:tasks", 0, -1) == [b"j-1"]
        assert redis.zrange("storage:d-2:tasks", 0, -1) == [b"j-1"]

    def test_ordering_is_by_score_newest_last(self, redis):
        for i, jid in enumerate(["old", "mid", "new"]):
            index_task(redis, _job(jid, enqueued_at=_dt(100 + i)), ["d-1"])
        assert redis.zrange("storage:d-1:tasks", 0, -1) == [b"old", b"mid", b"new"]

    def test_reindexing_the_same_job_does_not_duplicate_it(self, redis):
        index_task(redis, _job("j-1", enqueued_at=_dt(100)), ["d-1"])
        index_task(redis, _job("j-1", enqueued_at=_dt(200)), ["d-1"])
        assert redis.zcard("storage:d-1:tasks") == 1

    def test_no_owner_is_a_no_op(self, redis):
        index_task(redis, _job("j-1", enqueued_at=_dt(100)), [])
        index_task(redis, _job("j-2", enqueued_at=_dt(100)), [None])
        assert redis.keys("*") == []

    def test_the_media_namespace_is_written_the_same_way(self, redis):
        index_task(redis, _job("j-1", enqueued_at=_dt(100)), ["m-1"], kind="media")
        assert redis.zrange("media:m-1:tasks", 0, -1) == [b"j-1"]


class TestTheCapComesFromTheServer:
    """Not a round number, and not the threshold either: each write ZADDs
    before it trims, so a set capped AT the threshold momentarily holds one
    member too many and Redis converts it to a skiplist — permanently, because
    it never converts back. One below keeps every index in the cheap encoding.
    """

    def test_it_is_one_below_the_servers_listpack_threshold(self):
        assert index_cap(_FakeRedis(listpack_max=128)) == 127

    def test_it_follows_a_server_that_tuned_the_threshold(self):
        assert index_cap(_FakeRedis(listpack_max=64)) == 63

    def test_a_server_that_will_not_answer_falls_back_to_the_redis_default(self):
        assert index_cap(_FakeRedis(listpack_max=None)) == 127

    def test_a_nonsensical_threshold_is_refused(self):
        """A cap of zero would empty every index on the next write."""
        assert index_cap(_FakeRedis(listpack_max=0)) == 127

    def test_the_cap_never_degenerates_to_zero(self):
        assert index_cap(_FakeRedis(listpack_max=1)) == 1

    def test_it_is_resolved_once_not_on_every_write(self):
        """A CONFIG GET per index write would double the cost of a write that
        is otherwise a single round trip."""
        redis = _FakeRedis()
        calls = []
        redis.config_get = lambda name: calls.append(name) or {name: "128"}
        for _ in range(5):
            index_task(redis, _job("j-1", enqueued_at=_dt(100)), ["d-1"])
        assert len(calls) == 1


class TestRankCap:
    def test_the_set_is_capped_to_the_newest_n(self, redis):
        cap = index_cap(redis)
        for i in range(cap + 25):
            index_task(redis, _job(f"j-{i:04d}", enqueued_at=_dt(1000 + i)), ["d-1"])
        assert redis.zcard("storage:d-1:tasks") == cap

    def test_the_oldest_are_the_ones_dropped(self, redis):
        cap = index_cap(redis)
        for i in range(cap + 5):
            index_task(redis, _job(f"j-{i:04d}", enqueued_at=_dt(1000 + i)), ["d-1"])
        members = [m.decode() for m in redis.zrange("storage:d-1:tasks", 0, -1)]
        assert members[0] == "j-0005"
        assert members[-1] == f"j-{cap + 4:04d}"

    def test_no_clock_is_introduced(self, redis):
        """No EXPIRE, ever: it is per key, so every new task on a busy disk
        refreshes it and a member outlives its own job."""
        index_task(redis, _job("j-1", enqueued_at=_dt(100)), ["d-1"])
        assert redis.ttl("storage:d-1:tasks") == -1


class TestRead:
    def test_newest_first(self, redis):
        for i, jid in enumerate(["old", "mid", "new"]):
            index_task(redis, _job(jid, enqueued_at=_dt(100 + i)), ["d-1"])
        _alive(redis, "old", "mid", "new")
        assert owner_task_ids(redis, "d-1") == ["new", "mid", "old"]

    def test_a_disk_with_no_tasks_reads_empty(self, redis):
        assert owner_task_ids(redis, "never-seen") == []

    def test_a_member_whose_job_is_gone_is_dropped_from_the_answer(self, redis):
        for jid in ("alive-1", "gone", "alive-2"):
            index_task(redis, _job(jid, enqueued_at=_dt(100)), ["d-1"])
        _alive(redis, "alive-1", "alive-2")
        assert set(owner_task_ids(redis, "d-1")) == {"alive-1", "alive-2"}

    def test_and_is_lazily_removed_from_the_index(self, redis):
        for jid in ("alive-1", "gone"):
            index_task(redis, _job(jid, enqueued_at=_dt(100)), ["d-1"])
        _alive(redis, "alive-1")
        owner_task_ids(redis, "d-1")
        assert redis.zrange("storage:d-1:tasks", 0, -1) == [b"alive-1"]

    def test_an_index_whose_jobs_are_all_gone_reads_empty_and_empties(self, redis):
        index_task(redis, _job("gone", enqueued_at=_dt(100)), ["d-1"])
        assert owner_task_ids(redis, "d-1") == []
        assert redis.zcard("storage:d-1:tasks") == 0

    def test_media_reads_from_its_own_namespace(self, redis):
        index_task(redis, _job("j-1", enqueued_at=_dt(100)), ["m-1"], kind="media")
        _alive(redis, "j-1")
        assert owner_task_ids(redis, "m-1", kind="media") == ["j-1"]
        assert owner_task_ids(redis, "m-1", kind="storage") == []


class TestFailureIsNeverFatal:
    """Indexing is bookkeeping beside the task, not part of creating it. A redis
    blip must not fail the operation the user asked for."""

    def test_a_write_failure_does_not_raise(self):
        conn = MagicMock()
        conn.pipeline.side_effect = RuntimeError("redis down")
        index_task(conn, _job("j-1"), ["d-1"])

    def test_a_read_failure_reads_empty(self):
        conn = MagicMock()
        conn.zrevrange.side_effect = RuntimeError("redis down")
        assert owner_task_ids(conn, "d-1") == []
