# SPDX-License-Identifier: AGPL-3.0-or-later

"""At the heavy cap a governed worker still dequeues deletes, on a real Redis and rq."""

from __future__ import annotations

import json

import pytest
from isardvdi_common.lib.governed_worker import (
    GOVERNOR_CONFIG_KEY,
    HEAVY_RUNNING_KEY,
    GovernedWorker,
)
from rq import Queue
from rq.job import Job, JobStatus

POOL = "default"
CATEGORY = "test-cat-reclaim"
TIERS = ("template", "maintenance", "reclaim", "background")


def _psi(tmp_path, name, value):
    path = tmp_path / name
    path.write_text(f"some avg10={value} avg60=0 avg300=0 total=0\n")
    return str(path)


@pytest.fixture
def psi(tmp_path, monkeypatch):
    """Point the worker's PSI readings at files the test writes."""

    def set_pressure(value):
        for kind in ("CPU", "IO", "MEM"):
            monkeypatch.setenv(
                f"STORAGE_GOVERNOR_{kind}_PSI_PATH",
                _psi(tmp_path, kind.lower(), value),
            )

    return set_pressure


def _fill_the_heavy_cap(connection):
    # the slot's job must be live, or the leak reconcile prunes it
    connection.set(GOVERNOR_CONFIG_KEY, json.dumps({"max_heavy": 1, "backoff": 1}))
    busy = Job.create("builtins.len", args=([],), connection=connection)
    busy.save()
    busy.set_status(JobStatus.STARTED)
    connection.sadd(HEAVY_RUNNING_KEY, busy.id)
    return busy.id


def _lanes(multitenancy):
    if multitenancy:
        return {tier: f"storage.{POOL}.{CATEGORY}.{tier}" for tier in TIERS}
    return {tier: f"storage.{POOL}.{tier}" for tier in TIERS}


def _worker(connection, multitenancy):
    worker = GovernedWorker(
        [Queue(f"storage.{POOL}.{tier}", connection=connection) for tier in TIERS],
        connection=connection,
    )
    worker.multitenancy = multitenancy
    worker._refresh_live_config()
    return worker


@pytest.mark.parametrize("multitenancy", [True, False], ids=["fair", "flat"])
def test_a_delete_is_dequeued_while_the_heavy_cap_is_full(
    scratch_redis, psi, multitenancy
):
    """a main: the cap hides every deferrable lane, so the delete is never dequeued."""
    psi(1.0)
    busy = _fill_the_heavy_cap(scratch_redis)
    lanes = _lanes(multitenancy)
    maintenance = Queue(lanes["maintenance"], connection=scratch_redis)
    reclaim = Queue(lanes["reclaim"], connection=scratch_redis)
    move = maintenance.enqueue("builtins.len", [])
    delete = reclaim.enqueue("builtins.len", [])

    worker = _worker(scratch_redis, multitenancy)
    result = worker.dequeue_job_and_maintain_ttl(10, max_idle_time=2)

    assert result is not None, (
        "the worker served nothing at the heavy cap; the delete is still "
        f"queued ({reclaim.count} on {reclaim.name})"
    )
    job, queue = result
    assert job.id == delete.id, (
        f"expected the delete {delete.id} from {reclaim.name}, "
        f"got {job.id} from {queue.name}"
    )
    assert (
        move.id in maintenance.job_ids
    ), f"the maintenance job left its lane at the cap: {maintenance.job_ids}"
    slots = {m.decode() for m in scratch_redis.smembers(HEAVY_RUNNING_KEY)}
    assert slots == {busy}, f"a delete took a heavy slot: {slots}"
    reason = worker._defer_background()
    assert reason == "at_cap", f"expected the poll deferred for at_cap, got {reason!r}"


@pytest.mark.parametrize("multitenancy", [True, False], ids=["fair", "flat"])
def test_under_pressure_the_delete_still_waits(scratch_redis, psi, multitenancy):
    """Guard (passes on main too): PSI above the limit still hides reclaim."""
    psi(99.0)
    lanes = _lanes(multitenancy)
    reclaim = Queue(lanes["reclaim"], connection=scratch_redis)
    delete = reclaim.enqueue("builtins.len", [])
    scratch_redis.set(GOVERNOR_CONFIG_KEY, json.dumps({"backoff": 1}))

    worker = _worker(scratch_redis, multitenancy)
    reason = worker._defer_background()
    assert reason, f"expected the poll deferred under PSI, got {reason!r}"

    result = worker.dequeue_job_and_maintain_ttl(10, max_idle_time=2)

    assert (
        result is None
    ), f"under PSI the worker served {result[0].id} from {result[1].name}"
    assert (
        delete.id in reclaim.job_ids
    ), f"the delete left its lane under PSI: {reclaim.job_ids}"
