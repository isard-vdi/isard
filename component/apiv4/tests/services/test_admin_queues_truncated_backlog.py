#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``truncated_lanes_with_backlog``: the part of a capped lane scan that hides work."""

import pytest
from api.services.admin import queues as mod


class _Pipe:
    def __init__(self, parent):
        self.parent = parent
        self.ops = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def llen(self, key):
        self.ops.append(("llen", key))

    def zcard(self, key):
        self.ops.append(("zcard", key))

    def execute(self):
        self.parent.executions += 1
        if self.parent.fail_on_execution == self.parent.executions:
            raise ConnectionError("redis went away")
        return [getattr(self.parent, op)(key) for op, key in self.ops]


class _FakeRedis:
    def __init__(self, lists=None, zsets=None, extra_queues=()):
        self.lists = lists or {}  # lane name -> depth
        self.zsets = zsets or {}  # full registry key -> size
        self.extra = set(extra_queues)  # registered lanes with nothing anywhere
        self.executions = 0
        self.fail_on_execution = None

    def smembers(self, key):
        assert key == "rq:queues"
        names = set(self.lists) | self.extra
        names |= {k.split(":", 2)[2] for k in self.zsets}
        return {f"rq:queue:{n}".encode() for n in names}

    def llen(self, key):
        return self.lists.get(key[len("rq:queue:") :], 0)

    def zcard(self, key):
        return self.zsets.get(key, 0)

    def pipeline(self):
        return _Pipe(self)


@pytest.fixture
def cap_two(monkeypatch):
    monkeypatch.setattr(mod, "MAX_LANES", 2)


def test_a_cut_of_empty_lanes_hides_nothing(cap_two):
    conn = _FakeRedis(
        lists={"storage.a.bulk": 3, "storage.b.bulk": 1},
        extra_queues=[f"storage.p{i}.c{i}.reclaim" for i in range(5)],
    )

    lanes, truncated, with_backlog = mod._storage_lane_scan(conn)

    assert len(lanes) == 2
    assert truncated == 5
    assert with_backlog == 0


@pytest.mark.parametrize("registry", ["rq:wip", "rq:deferred", "rq:scheduled"])
def test_a_cut_lane_with_an_empty_list_but_a_registered_job_is_hidden_work(
    cap_two, registry
):
    """The busiest-first order is by LLEN, so a lane whose job is running or
    waiting sorts with the empty ones and is the first to be cut."""
    conn = _FakeRedis(
        lists={"storage.a.bulk": 3, "storage.b.bulk": 1},
        zsets={f"{registry}:storage.p.c.reclaim": 1},
        extra_queues=["storage.q.c.reclaim"],
    )

    _lanes, truncated, with_backlog = mod._storage_lane_scan(conn)

    assert truncated == 2
    assert with_backlog == 1


def test_a_cut_lane_with_queued_jobs_is_hidden_work(cap_two):
    conn = _FakeRedis(
        lists={"storage.a.bulk": 9, "storage.b.bulk": 5, "storage.c.bulk": 2},
        extra_queues=["storage.d.bulk"],
    )

    _lanes, truncated, with_backlog = mod._storage_lane_scan(conn)

    assert truncated == 2
    assert with_backlog == 1


def test_the_failed_registry_alone_is_not_hidden_work(cap_two):
    """A failed job is a result, not pending work: it is in the problem-task
    listing whatever the lane scan keeps."""
    conn = _FakeRedis(
        lists={"storage.a.bulk": 3, "storage.b.bulk": 1},
        zsets={"rq:failed:storage.p.c.reclaim": 4},
    )

    _lanes, truncated, with_backlog = mod._storage_lane_scan(conn)

    assert truncated == 1
    assert with_backlog == 0


def test_no_cut_costs_no_registry_reads(cap_two):
    conn = _FakeRedis(lists={"storage.a.bulk": 3})

    lanes, truncated, with_backlog = mod._storage_lane_scan(conn)

    assert (len(lanes), truncated, with_backlog) == (1, 0, 0)
    assert conn.executions == 1  # the LLEN sort only


def test_a_redis_error_on_the_backlog_read_counts_every_cut_lane(cap_two):
    """Fail closed: an error must not turn a cut that hides work into a quiet
    one. The bare count is unaffected."""
    conn = _FakeRedis(
        lists={"storage.a.bulk": 3, "storage.b.bulk": 1},
        extra_queues=["storage.p.c.reclaim", "storage.q.c.reclaim"],
    )
    conn.fail_on_execution = 2  # the LLEN sort works, the backlog read fails

    _lanes, truncated, with_backlog = mod._storage_lane_scan(conn)

    assert truncated == 2
    assert with_backlog == 2


def test_the_two_value_snapshot_keeps_its_shape(cap_two):
    """The listing callers unpack two values; the split is for the gauges."""
    conn = _FakeRedis(
        lists={"storage.a.bulk": 3, "storage.b.bulk": 1},
        extra_queues=["storage.p.c.reclaim"],
    )

    lanes, truncated = mod._storage_lane_snapshot(conn)

    assert len(lanes) == 2
    assert truncated == 1
