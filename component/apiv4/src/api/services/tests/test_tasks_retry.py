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
from unittest.mock import MagicMock, patch

import pytest
from api.services.error import Error
from api.services.tasks import TaskService
from rq.job import JobStatus

LANE = "storage.default.default.maintenance"


def _task(job_status=JobStatus.FAILED, status="failed", queue=LANE, task_id="t-1"):
    task = MagicMock(name="task")
    task.id = task_id
    task.status = status
    task.job_status = job_status
    task.queue = queue
    task.to_dict.return_value = {"id": task_id}
    return task


class TestRetryTask:
    def test_retries_a_task_whose_own_job_failed(self):
        task = _task()
        with patch("api.services.tasks.Task") as Task:
            Task.exists.return_value = True
            Task.return_value = task
            assert TaskService.retry_task("t-1") == {"id": "t-1"}
        task.retry.assert_called_once_with()

    def test_refuses_when_the_failure_is_elsewhere_in_the_chain(self):
        """The addressed job FINISHED; only the chain is ``failed``. Requeueing
        it raises inside rq (it is not a failed-registry member) and would also
        re-run work that succeeded — refuse with a precondition instead."""
        task = _task(job_status=JobStatus.FINISHED)
        with patch("api.services.tasks.Task") as Task:
            Task.exists.return_value = True
            Task.return_value = task
            with pytest.raises(Error) as excinfo:
                TaskService.retry_task("t-1")
        assert excinfo.value.status_code == 428
        task.retry.assert_not_called()

    def test_refuses_a_job_on_a_lane_with_no_worker_fleet(self):
        """``core`` steps are executed in-process by the change-handler and no
        rq worker subscribes to that queue: re-enqueueing one strands it."""
        task = _task(queue="core")
        with patch("api.services.tasks.Task") as Task:
            Task.exists.return_value = True
            Task.return_value = task
            with pytest.raises(Error) as excinfo:
                TaskService.retry_task("t-1")
        assert excinfo.value.status_code == 428
        task.retry.assert_not_called()


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
