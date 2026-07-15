# SPDX-License-Identifier: AGPL-3.0-or-later

"""Real-redis (NO-mock) tests for the migration orphan-RESUME path.

The production trap: a storage task whose WORKER DIES mid-execution stays rq
``STARTED`` until the 12h task timeout — ``Job.get_status()`` never flips,
because the only thing that changes is that its ``StartedJobRegistry`` heartbeat
score stops being refreshed. Without detection the saga wedges for 12h.

These exercise the REAL ``job_status`` / ``decide_item_action`` /
``verify_gate_state`` against a REAL redis and real rq ``Job`` /
``StartedJobRegistry`` (no ``_RqLikeTask`` mock). A dead worker is simulated by
writing an already-expired heartbeat score into the registry. Skipped when no
redis is reachable (plain CI image); run live on ``isard-network``.
"""

from time import time

import isardvdi_common.lib.storage.migration_run as mr
import pytest
import redis as redis_lib
from isardvdi_common.connections.redis_urls import rq_url
from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.models.task import Task
from rq.job import Job, JobStatus
from rq.registry import StartedJobRegistry

# a queue NO worker consumes, so the real storage worker never runs our probe job
QUEUE = "storage.orphan-resume-test.default"


def _conn_or_skip():
    try:
        conn = redis_lib.from_url(rq_url())
        conn.ping()
        return conn
    except Exception:
        pytest.skip("no redis reachable (run on isard-network)")


@pytest.fixture
def started_job():
    """Enqueue a real ``task.move`` and force it ``STARTED`` the way a worker
    would, returning ``(task_id, conn, registry)``. The score is set per-test to
    simulate a live / abandoned / within-grace worker. Cleans up after."""
    conn = _conn_or_skip()
    t = Task(
        task="move",
        queue=QUEUE,
        user_id="orphan-resume-test",
        job_kwargs={
            "kwargs": {
                "origin_path": "/orphan/src.qcow2",
                "destination_path": "/orphan/dst.qcow2",
                "method": "rsync",
            }
        },
    )
    tid = t.id
    job = Job.fetch(tid, connection=conn)
    job.set_status(JobStatus.STARTED)  # a worker has picked it up
    registry = StartedJobRegistry(QUEUE, connection=conn)
    yield tid, conn, registry
    try:
        conn.zrem(registry.key, tid)
        Job.fetch(tid, connection=conn).delete()
    except Exception:
        pass


def _set_score(conn, registry, tid, score):
    conn.zadd(registry.key, {tid: score})


def test_abandoned_started_reports_gone_and_resumes(started_job):
    tid, conn, registry = started_job
    # dead worker: heartbeat score expired well past the grace margin
    _set_score(conn, registry, tid, time() - (mr.ABANDON_GRACE_S + 100))

    # THE PRODUCTION TRAP: rq still says STARTED ...
    assert Job.fetch(tid, connection=conn).get_status() == JobStatus.STARTED
    # ... but job_status reports it GONE so the saga can resume.
    assert mr.job_status(tid) is None

    # a moving disk on this abandoned task RESUMES (re-enqueue the idempotent move)
    moving = {"state": "moving", "move_task_id": tid, "topo_index": 0}
    assert mig.decide_item_action(moving, mr.job_status) == "start_move"


def test_live_started_is_not_abandoned(started_job):
    tid, conn, registry = started_job
    # live worker: heartbeat score well in the future
    _set_score(conn, registry, tid, time() + 3600)

    assert Job.fetch(tid, connection=conn).get_status() == JobStatus.STARTED
    # NO false positive: a live STARTED job is reported started -> wait
    assert mr.job_status(tid) == "started"
    moving = {"state": "moving", "move_task_id": tid, "topo_index": 0}
    assert mig.decide_item_action(moving, mr.job_status) == "wait"


def test_recently_expired_within_grace_is_not_abandoned(started_job):
    tid, conn, registry = started_job
    # expired only a moment ago, inside the grace window -> NOT yet abandoned
    _set_score(conn, registry, tid, time() - max(1, mr.ABANDON_GRACE_S // 2))
    assert mr.job_status(tid) == "started"


def test_abandoned_verify_resumes_the_gate(started_job):
    tid, conn, registry = started_job
    _set_score(conn, registry, tid, time() - (mr.ABANDON_GRACE_S + 100))
    # an abandoned verify task makes the gate RESUME (re-run the check), not wedge
    assert mig.verify_gate_state({"verify_task_id": tid}, mr.job_status) == "start"


def test_no_release_until_verify_actually_finishes(started_job):
    tid, conn, registry = started_job
    item = {
        "state": "rebased",
        "storage_id": "s-r",
        "tree_id": "s-r",
        "topo_index": 0,
        "src_path": "/a/s-r.qcow2",
        "dst_path": "/b/s-r.qcow2",
        "verify_task_id": tid,
    }
    # abandoned verify -> the saga re-enqueues the gate; NO db_update/release
    _set_score(conn, registry, tid, time() - (mr.ABANDON_GRACE_S + 100))
    _it, action = mig.tree_next([item], mr.job_status)
    assert action == "start_verify"

    # once the verify task actually FINISHES the pass is persisted (mark_verified)
    # so it survives the rq job result expiring; only then is the row repointed
    # (db_update), and the source delete (release) follows once it is committed
    Job.fetch(tid, connection=conn).set_status(JobStatus.FINISHED)
    conn.zrem(registry.key, tid)
    _it, action = mig.tree_next([item], mr.job_status)
    assert action == "mark_verified"
    item["verify_passed"] = True
    _it, action = mig.tree_next([item], mr.job_status)
    assert action == "db_update"
    item["state"] = "db_updated"
    _it, action = mig.tree_next([item], mr.job_status)
    assert action == "release"
