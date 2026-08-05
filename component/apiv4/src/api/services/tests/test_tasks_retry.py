#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Retry admission tests for ``TaskService``.

``Task.status`` is the status of the whole dependency CHAIN, and
``global_status`` ranks FAILED above FINISHED. A chain whose core dependent
failed therefore reports ``failed`` on its FINISHED root too, so the root sailed
through ``retry_task``'s gate and rq was asked to requeue a job that never
failed. The bulk endpoint had the same hole and hid every outcome behind a bare
``except: pass``.
"""

import logging
import os
import uuid
from unittest.mock import MagicMock, patch

import pytest
from api.services.error import Error
from api.services.tasks import TaskService
from rq.job import JobStatus

LANE = "storage.default.default.maintenance"


def _task(
    job_status=JobStatus.FAILED,
    status="failed",
    queue=LANE,
    task_id="t-1",
    dependents=(),
):
    task = MagicMock(name="task")
    task.id = task_id
    task.status = status
    task.job_status = job_status
    task.queue = queue
    task.dependents = list(dependents)
    task.to_dict.return_value = {"id": task_id}
    return task


class TestRetryTask:
    def test_retries_a_task_whose_own_job_failed(self):
        task = _task()
        with patch("api.services.tasks.tasks_from_ids", return_value=[task]):
            assert TaskService.retry_task("t-1") == {"id": "t-1"}
        task.retry.assert_called_once_with()

    def test_refuses_when_the_failure_is_elsewhere_in_the_chain(self):
        """The addressed job FINISHED; only the chain is ``failed``. Requeueing
        it raises inside rq (it is not a failed-registry member) and would also
        re-run work that succeeded — refuse with a precondition instead."""
        task = _task(job_status=JobStatus.FINISHED)
        with patch("api.services.tasks.tasks_from_ids", return_value=[task]):
            with pytest.raises(Error) as excinfo:
                TaskService.retry_task("t-1")
        assert excinfo.value.status_code == 428
        task.retry.assert_not_called()

    def test_retries_a_failed_root_whose_chain_reads_canceled(self):
        """The two gates must not contradict each other.

        Cancelling a chain whose root had already FAILED leaves the root job
        FAILED and its dependents CANCELED, and ``global_status`` ranks
        CANCELED above FAILED — so the chain reads ``canceled`` on a root that
        is genuinely retryable. ``_retry_refusal`` (per-job, the predicate the
        row's own display and the bulk path use) says yes; the chain-global
        gate said 428. Retry must defer to the one predicate."""
        task = _task(job_status=JobStatus.FAILED, status=JobStatus.CANCELED)
        assert TaskService._retry_refusal(task) is None
        with patch("api.services.tasks.tasks_from_ids", return_value=[task]):
            assert TaskService.retry_task("t-1") == {"id": "t-1"}
        task.retry.assert_called_once_with()

    def test_refuses_when_a_direct_dependent_is_canceled(self):
        """rq admits a dependent only when its status is not CANCELED (proved
        in ``TestRqDependentAdmission``), so retrying this root would re-run
        the disk operation while the cancelled dependents that finalise it stay
        cancelled — the operation happens and nothing closes it out."""
        dependent = _task(job_status=JobStatus.CANCELED, task_id="dep-1")
        task = _task(dependents=[dependent])
        with patch("api.services.tasks.tasks_from_ids", return_value=[task]):
            with pytest.raises(Error) as excinfo:
                TaskService.retry_task("t-1")
        assert excinfo.value.status_code == 428
        assert "dep-1" in str(excinfo.value)
        task.retry.assert_not_called()

    def test_allows_a_retry_whose_dependents_are_still_deferred(self):
        """Only CANCELED dependents block: a DEFERRED one is exactly what rq
        will promote once the root succeeds."""
        dependent = _task(job_status=JobStatus.DEFERRED, task_id="dep-1")
        task = _task(dependents=[dependent])
        with patch("api.services.tasks.tasks_from_ids", return_value=[task]):
            assert TaskService.retry_task("t-1") == {"id": "t-1"}
        task.retry.assert_called_once_with()

    def test_refuses_a_job_on_a_lane_with_no_worker_fleet(self):
        """``core`` steps are executed in-process by the change-handler and no
        rq worker subscribes to that queue: re-enqueueing one strands it."""
        task = _task(queue="core")
        with patch("api.services.tasks.tasks_from_ids", return_value=[task]):
            with pytest.raises(Error) as excinfo:
                TaskService.retry_task("t-1")
        assert excinfo.value.status_code == 428
        task.retry.assert_not_called()


class TestRqDependentAdmission:
    """The premise the CANCELED-dependent refusal rests on, proved against the
    rq we actually ship instead of taken on trust.

    Needs a reachable redis (an unused db, default 15) — skipped where there is
    none, which is why the refusal itself is also covered by a unit test above.
    """

    @staticmethod
    def _queue():
        redis = pytest.importorskip("redis")
        from rq import Queue

        connection = redis.Redis(
            host=os.environ.get("REDIS_HOST", "isard-redis"),
            port=int(os.environ.get("REDIS_PORT", 6379)),
            password=os.environ.get("REDIS_PASSWORD") or None,
            db=int(os.environ.get("RQ_PROOF_REDIS_DB", 15)),
        )
        try:
            connection.ping()
        except Exception as exc:
            pytest.skip(f"no redis to prove rq's behaviour against: {exc}")
        return Queue(f"rq-proof-{uuid.uuid4().hex[:8]}", connection=connection)

    def test_rq_skips_a_canceled_dependent_and_enqueues_a_deferred_one(self):
        """``Queue.enqueue_dependents`` admits a dependent only when its status
        is not CANCELED. So a root whose chain was cancelled re-runs its disk
        operation while the dependents that would have finalised it never
        re-run: the operation happens and nothing closes it out."""
        queue = self._queue()
        root = queue.enqueue(print, "root")
        canceled = queue.enqueue(print, "canceled", depends_on=root)
        deferred = queue.enqueue(print, "deferred", depends_on=root)
        try:
            canceled.cancel()
            assert canceled.get_status(refresh=True) == JobStatus.CANCELED
            assert deferred.get_status(refresh=True) == JobStatus.DEFERRED
            root.set_status(JobStatus.FINISHED)

            queue.enqueue_dependents(root)

            queued = queue.job_ids
            assert deferred.id in queued, "a DEFERRED dependent must be promoted"
            assert canceled.id not in queued, "rq must not promote a CANCELED one"
            assert canceled.get_status(refresh=True) == JobStatus.CANCELED
        finally:
            for job in (root, canceled, deferred):
                job.delete()
            queue.delete(delete_jobs=True)


class TestRetryAllFailedTasks:
    def test_skips_non_retryable_tasks_and_keeps_going(self):
        retryable = _task(task_id="ok-1")
        chain_only = _task(job_status=JobStatus.FINISHED, task_id="skip-1")
        with patch("api.services.tasks.Task") as Task:
            Task.get_failed_storage_tasks.return_value = [chain_only, retryable]
            summary = TaskService.retry_all_failed_tasks()
        chain_only.retry.assert_not_called()
        retryable.retry.assert_called_once_with()
        assert summary["retried"] == 1
        assert summary["skipped"] == 1
        assert summary["errors"] == 0

    def test_counts_a_stranded_lane_refusal_as_skipped(self):
        """``Task.retry``'s own consumer gate raises a typed 429; that is a
        deliberate refusal, not a batch error."""
        stranded = _task(task_id="stranded-1")
        stranded.retry.side_effect = Error("too_many_requests", "no consumer")
        with patch("api.services.tasks.Task") as Task:
            Task.get_failed_storage_tasks.return_value = [stranded]
            summary = TaskService.retry_all_failed_tasks()
        assert summary == {"retried": 0, "skipped": 1, "errors": 0}

    def test_one_raising_task_does_not_abort_the_batch_and_is_logged(self, caplog):
        """The blanket ``except: pass`` made a fleet-wide failure look like a
        successful bulk retry. Every unexpected error must be logged."""
        boom = _task(task_id="boom-1")
        boom.retry.side_effect = RuntimeError("redis down")
        healthy = _task(task_id="ok-1")
        with patch("api.services.tasks.Task") as Task:
            Task.get_failed_storage_tasks.return_value = [boom, healthy]
            with caplog.at_level(logging.ERROR, logger="api.services.tasks"):
                summary = TaskService.retry_all_failed_tasks()
        healthy.retry.assert_called_once_with()
        assert summary["errors"] == 1
        assert summary["retried"] == 1
        assert "boom-1" in caplog.text
