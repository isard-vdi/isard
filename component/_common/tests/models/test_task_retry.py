#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin-down tests for ``Task.retry`` (redis mocked out — mechanics only).

Two production failures are pinned here:

* rq's ``Job.requeue`` is driven by ``FailedJobRegistry``: it ``ZREM``s the job
  from the registry zset and raises ``InvalidJobOperation`` when nothing was
  removed. A chain step marked FAILED with ``Job.set_status`` (the
  change-handler's in-process finalize path) only ever gets the status hash
  field, never registry membership — so requeueing such a job always raised.
* ``requeue`` re-enqueues on ``job.origin`` unconditionally. When that lane lost
  its consumer (pool disabled / workers drained) the job moves from ``failed``
  (listed, retryable) to ``queued`` on a lane nothing serves — it disappears
  from the failed listing and never runs again.
"""

from unittest.mock import MagicMock, patch

import pytest
from isardvdi_common.helpers.error_base import ErrorBase
from isardvdi_common.models.task import Task
from rq.exceptions import InvalidJobOperation

LANE = "storage.default.default.maintenance"


def _task(origin=LANE, requeue_side_effect=None):
    """A ``Task`` wrapping a mocked RQ ``Job`` — no redis is touched."""
    job = MagicMock(name="job")
    job.id = "job-1"
    job.origin = origin
    job.meta = {}
    if requeue_side_effect is not None:
        job.requeue.side_effect = requeue_side_effect
    with patch("isardvdi_common.models.task.Job") as Job:
        Job.fetch.return_value = job
        task = Task("job-1")
    return task, job


def test_retry_uses_rq_requeue_for_a_registry_member():
    """The normal path is unchanged: a job the failed registry knows about is
    requeued by rq itself (which restores the registry invariants)."""
    task, job = _task()
    with patch("isardvdi_common.models.task.Queue") as Queue, patch(
        "isardvdi_common.lib.queue_coverage.check_no_consumer"
    ):
        task.retry()
    job.requeue.assert_called_once_with()
    Queue.assert_not_called()


def test_retry_reenqueues_a_job_marked_failed_without_registry_membership():
    """A hash-only FAILED mark leaves the job out of ``FailedJobRegistry``, so
    rq's ``requeue`` raises ``InvalidJobOperation``. That must not surface as a
    500: fall back to enqueuing the job on its own origin lane."""
    task, job = _task(requeue_side_effect=InvalidJobOperation())
    queue = MagicMock(name="queue")
    with patch("isardvdi_common.models.task.Queue") as Queue, patch(
        "isardvdi_common.lib.queue_coverage.check_no_consumer"
    ):
        Queue.return_value = queue
        task.retry()
    Queue.assert_called_once_with(LANE, connection=Task._redis)
    queue._enqueue_job.assert_called_once_with(job)
    # The previous run's outcome must be cleared, exactly as rq's own
    # FailedJobRegistry.requeue does after its ZREM.
    assert job.started_at is None
    assert job.ended_at is None
    job.save.assert_called_once_with()


def test_retry_refuses_a_lane_with_no_live_consumer():
    """A failed job whose lane has no consumer must stay failed: re-enqueueing
    it would hide it from the failed listing forever."""
    task, job = _task()
    queue = MagicMock(name="queue")
    with patch("isardvdi_common.models.task.Queue") as Queue, patch(
        "isardvdi_common.lib.queue_coverage.check_no_consumer",
        side_effect=ErrorBase("too_many_requests", "no consumer"),
    ):
        Queue.return_value = queue
        with pytest.raises(ErrorBase) as excinfo:
            task.retry()
    assert excinfo.value.status_code == 429
    job.requeue.assert_not_called()
    queue._enqueue_job.assert_not_called()


def test_retry_gates_the_jobs_own_lane():
    """The coverage gate must be asked about the lane the job will land on."""
    task, _job = _task()
    with patch("isardvdi_common.models.task.Queue"), patch(
        "isardvdi_common.lib.queue_coverage.check_no_consumer"
    ) as check:
        task.retry()
    check.assert_called_once_with(Task._redis, LANE)
