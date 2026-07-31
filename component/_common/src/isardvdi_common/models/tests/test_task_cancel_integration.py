# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin-down tests for ``Task.cancel()``'s pub/sub integration.

The Task class is heavyweight (RQ ``Job``, redis-backed metadata, lazy
properties). We don't try to exercise it end-to-end here — that's what
the storage integration suite does. Instead we drive ``cancel()``
directly on a bare instance with the redis side faked out, so the unit
of behavior under test is just:

* a ``task:cancel:<id>`` pub/sub signal is published for every chain
  member that is still running,
* a transient pub/sub failure does NOT prevent the RQ-level
  ``job.cancel()`` from running (best-effort contract documented in the
  docstring),
* the RQ cancel NEVER enqueues dependents.

The chain-closure semantics themselves (which members get canceled, in
which order) are pinned in ``test_task_cancel_chain.py``.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from isardvdi_common.models.task import Task


def _bare_task_with(job_id: str) -> Task:
    """Build a ``Task`` instance whose ``id`` and job graph we fully
    control, without touching redis. ``Task.id`` is a property over
    ``self.job.id`` — set it via the mocked job."""
    t = Task.__new__(Task)
    fake_job = MagicMock()
    fake_job.id = job_id
    fake_job.meta = {"dependency_ids": [], "dependent_ids": []}
    return t, fake_job


def _cancel(task, job):
    """Run ``cancel()`` with the job graph resolving to ``job`` alone."""
    graph = {job.id: job}

    def _fetch(job_id, connection=None):
        return graph[job_id]

    with patch(
        "isardvdi_common.models.task.Job.fetch", side_effect=_fetch
    ), patch.object(Task, "_redis", MagicMock()), patch(
        "isardvdi_common.models.task.publish_canceled_event"
    ):
        task.cancel()


class TestTaskCancelPublishesSignal:
    @patch("isardvdi_common.helpers.task_cancel.request_task_cancel")
    def test_publishes_cancel_for_self_id(self, mock_publish):
        t, job = _bare_task_with("root-1")
        t.job = job

        _cancel(t, job)

        mock_publish.assert_called_once_with("root-1")
        # NEVER ``enqueue_dependents=True``: promoting a canceled chain's
        # dependents strands them QUEUED on the consumerless ``core``
        # queue, which ``Task.pending`` then reads as active work and the
        # storage is rejected with ``storage_pending_task`` forever.
        job.cancel.assert_called_once_with(enqueue_dependents=False)

    @patch(
        "isardvdi_common.helpers.task_cancel.request_task_cancel",
        side_effect=RuntimeError("redis offline"),
    )
    def test_publish_failure_does_not_prevent_rq_cancel(self, _mock_publish):
        """If pub/sub is briefly unreachable, the queued-job cancel
        path is still our best-effort fallback — RQ's cancel must run."""
        t, job = _bare_task_with("root-1")
        t.job = job

        # Must not raise.
        _cancel(t, job)

        job.cancel.assert_called_once_with(enqueue_dependents=False)

    @patch("isardvdi_common.helpers.task_cancel.request_task_cancel")
    def test_no_dependencies_still_publishes_and_cancels(self, mock_publish):
        t, job = _bare_task_with("root-1")
        t.job = job

        _cancel(t, job)

        mock_publish.assert_called_once_with("root-1")
        job.cancel.assert_called_once_with(enqueue_dependents=False)

    @patch("isardvdi_common.helpers.task_cancel.request_task_cancel")
    def test_cancel_does_not_hydrate_the_dependencies_property(self, _mock_publish):
        """The sweep walks the job graph directly (``meta`` ids + ``Job``),
        never the Task-hydrating ``dependencies`` property — that property
        skips ids whose hash is gone and would silently drop members."""
        t, job = _bare_task_with("root-1")
        t.job = job

        with patch.object(
            Task, "dependencies", new_callable=lambda: property(lambda self: 1 / 0)
        ):
            _cancel(t, job)

        job.cancel.assert_called_once_with(enqueue_dependents=False)
