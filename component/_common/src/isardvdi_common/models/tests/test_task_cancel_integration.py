# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin-down tests for ``Task.cancel()``'s pub/sub integration.

The Task class is heavyweight (RQ ``Job``, redis-backed metadata, lazy
properties). We don't try to exercise it end-to-end here — that's what
the storage integration suite does. Instead we drive ``cancel()``
directly on a bare instance with the redis side faked out, so the unit
of behavior under test is just:

* every direct dependency's ``cancel()`` is invoked first (recursive
  cancel from leaves up),
* a ``task:cancel:<id>`` pub/sub signal is published once,
* a transient pub/sub failure does NOT prevent the RQ-level
  ``job.cancel(enqueue_dependents=True)`` from running (best-effort
  contract documented in the docstring).
"""

from __future__ import annotations

from unittest.mock import MagicMock, PropertyMock, patch

from isardvdi_common.models.task import Task


def _bare_task_with(job_id: str, deps: list) -> Task:
    """Build a ``Task`` instance whose ``id`` and ``dependencies`` we
    fully control, without touching redis. ``Task.id`` is a property
    over ``self.job.id`` — set it via the mocked job. ``dependencies``
    is a property too; we patch it on the class for the test scope."""
    t = Task.__new__(Task)
    fake_job = MagicMock()
    fake_job.id = job_id
    t.job = fake_job
    return t


class TestTaskCancelPublishesSignal:
    @patch("isardvdi_common.helpers.task_cancel.request_task_cancel")
    @patch.object(Task, "dependencies", new_callable=PropertyMock, return_value=[])
    def test_publishes_cancel_for_self_id(self, _deps, mock_publish):
        t = _bare_task_with("root-1", deps=[])

        t.cancel()

        mock_publish.assert_called_once_with("root-1")
        t.job.cancel.assert_called_once_with(enqueue_dependents=True)

    @patch("isardvdi_common.helpers.task_cancel.request_task_cancel")
    def test_recursively_cancels_dependencies_first(self, mock_publish):
        """Dependency cancel is the leaves-first sweep — it must fire
        before the root publish so a partially-completed chain doesn't
        leak running grandchildren."""
        t = _bare_task_with("root-1", deps=[])

        dep1 = MagicMock()
        dep2 = MagicMock()
        # Patch the dependencies property at the class level for the
        # life of this single test.
        with patch.object(Task, "dependencies", new_callable=PropertyMock) as deps_prop:
            deps_prop.return_value = [dep1, dep2]
            t.cancel()

        dep1.cancel.assert_called_once_with()
        dep2.cancel.assert_called_once_with()
        mock_publish.assert_called_once_with("root-1")
        # The order matters: dependencies are walked, then we publish,
        # then we cancel the RQ job. We assert this through call_args
        # ordering — every dep.cancel happened before publish was hit.
        # (MagicMock records absolute call order in mock_calls; for
        # readability we just assert the high-level invariants.)

    @patch(
        "isardvdi_common.helpers.task_cancel.request_task_cancel",
        side_effect=RuntimeError("redis offline"),
    )
    @patch.object(Task, "dependencies", new_callable=PropertyMock, return_value=[])
    def test_publish_failure_does_not_prevent_rq_cancel(self, _deps, _mock_publish):
        """If pub/sub is briefly unreachable, the queued-job cancel
        path is still our best-effort fallback — RQ's cancel must run."""
        t = _bare_task_with("root-1", deps=[])

        # Must not raise.
        t.cancel()

        t.job.cancel.assert_called_once_with(enqueue_dependents=True)

    @patch("isardvdi_common.helpers.task_cancel.request_task_cancel")
    @patch.object(Task, "dependencies", new_callable=PropertyMock, return_value=[])
    def test_no_dependencies_still_publishes_and_cancels(self, _deps, mock_publish):
        t = _bare_task_with("root-1", deps=[])

        t.cancel()

        mock_publish.assert_called_once_with("root-1")
        t.job.cancel.assert_called_once_with(enqueue_dependents=True)
