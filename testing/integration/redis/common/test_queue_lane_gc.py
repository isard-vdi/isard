# SPDX-License-Identifier: AGPL-3.0-or-later

"""The storage lane GC on a real Redis with real rq queues, registries and workers."""

import time

import pytest
from isardvdi_common.lib import queue_lane_gc as gc
from isardvdi_common.lib.governed_worker import GovernedWorker
from isardvdi_common.lib.result_job import ResultJob
from rq import Queue, SimpleWorker, Worker
from rq.job import JobStatus
from rq.registry import (
    DeferredJobRegistry,
    FailedJobRegistry,
    ScheduledJobRegistry,
    StartedJobRegistry,
)

IDLE = [f"storage.p{i % 9}.c{i}.reclaim" for i in range(600)]
REGISTRIES = {
    "started": StartedJobRegistry,
    "deferred": DeferredJobRegistry,
    "scheduled": ScheduledJobRegistry,
    "failed": FailedJobRegistry,
}


def _registered(conn):
    return {m.decode() for m in conn.smembers("rq:queues")}


def _run(conn, now):
    conn.delete(gc.LANE_GC_LOCK_KEY)
    return gc.collect_empty_lanes(conn, now=now)


def _drained_lane(conn, name):
    """A lane left behind the way production leaves it: enqueued, then emptied."""
    queue = Queue(name, connection=conn, job_class=ResultJob)
    job = queue.enqueue("os.getpid")
    conn.lrem(queue.key, 0, job.id)
    job.delete()
    return queue


@pytest.fixture
def fleet(scratch_redis):
    conn = scratch_redis
    for name in IDLE:
        _drained_lane(conn, name)
    busy = {}
    queued = Queue("storage.pa.cq.bulk", connection=conn, job_class=ResultJob)
    queued.enqueue("os.getpid")
    busy["queued"] = queued.key
    for kind, registry in REGISTRIES.items():
        queue = _drained_lane(conn, f"storage.pa.c{kind}.reclaim")
        conn.zadd(registry(queue=queue).key, {f"job-{kind}": time.time() + 3600})
        busy[kind] = queue.key
    listened = _drained_lane(conn, "storage.pw.reclaim")
    worker = Worker([listened], connection=conn, name="lane-gc-listener")
    worker.register_birth()
    busy["worker"] = listened.key
    conn.sadd("rq:queues", "rq:queue:default")
    yield conn, busy
    worker.register_death()


def test_idle_lanes_go_and_lanes_with_work_stay(fleet):
    conn, busy = fleet
    assert len(_registered(conn)) == len(IDLE) + len(busy) + 1

    now = time.time()
    assert _run(conn, now)["removed"] == 0
    summary = _run(conn, now + gc.LANE_GC_GRACE_SECONDS + 1)

    assert summary["removed"] == len(IDLE)
    assert _registered(conn) == set(busy.values()) | {"rq:queue:default"}


def test_a_dead_worker_registration_does_not_keep_a_lane(scratch_redis):
    queue = _drained_lane(scratch_redis, "storage.pd.reclaim")
    worker = Worker([queue], connection=scratch_redis, name="lane-gc-dead")
    worker.register_birth()
    scratch_redis.delete(worker.key)  # its hash expired; the set member stays

    now = time.time()
    _run(scratch_redis, now)
    _run(scratch_redis, now + gc.LANE_GC_GRACE_SECONDS + 1)

    assert queue.key not in _registered(scratch_redis)


def test_an_enqueue_on_a_removed_lane_registers_it_and_the_job_runs(scratch_redis):
    queue = _drained_lane(scratch_redis, IDLE[0])
    now = time.time()
    _run(scratch_redis, now)
    _run(scratch_redis, now + gc.LANE_GC_GRACE_SECONDS + 1)
    assert queue.key not in _registered(scratch_redis)

    job = queue.enqueue("os.getpid")
    assert queue.key in _registered(scratch_redis)
    SimpleWorker([queue], connection=scratch_redis, job_class=ResultJob).work(
        burst=True
    )

    assert job.get_status(refresh=True) == JobStatus.FINISHED


def test_a_job_pushed_without_registering_gets_its_lane_back(scratch_redis):
    queue = _drained_lane(scratch_redis, IDLE[1])
    now = time.time()
    _run(scratch_redis, now)
    _run(scratch_redis, now + gc.LANE_GC_GRACE_SECONDS + 1)
    scratch_redis.rpush(queue.key, "pushed-after-the-removal")

    summary = _run(scratch_redis, now + gc.LANE_GC_GRACE_SECONDS + 600)

    assert summary["restored"] == 1
    assert queue.key in _registered(scratch_redis)


def test_the_worker_maintenance_runs_the_pass(scratch_redis):
    _drained_lane(scratch_redis, IDLE[2])
    worker = GovernedWorker(
        [Queue("storage.p1.background", connection=scratch_redis, job_class=ResultJob)],
        connection=scratch_redis,
        job_class=ResultJob,
    )
    scratch_redis.delete(gc.LANE_GC_LOCK_KEY)

    worker.clean_registries()

    assert scratch_redis.hexists(gc.LANE_GC_IDLE_SINCE_KEY, f"rq:queue:{IDLE[2]}")
    assert scratch_redis.exists(gc.LANE_GC_LOCK_KEY)
