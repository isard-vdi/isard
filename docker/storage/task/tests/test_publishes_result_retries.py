# SPDX-License-Identifier: AGPL-3.0-or-later

"""A raised attempt that RQ will retry must not be published as a failure.

`_publishes_result` announced `job_status="failed"` on EVERY raised attempt.
But rq only gives up once `retries_left` hits zero (`Job.should_retry`,
`worker.py:709`), so a transient error on a task created with `retry=3` --
`find` and `check_backing_chain` default to exactly that -- made the
change-handler run the chain's FAILURE branch and delete its core dependents
while rq was still going to run the task again. The successful retry then had
no finalizers left to drive.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _job(retries_left=None):
    return SimpleNamespace(
        id="job-1",
        origin="storage.pool.maintenance",
        connection=MagicMock(),
        retries_left=retries_left,
    )


def _decorated(exc=None):
    import task as task_mod

    @task_mod._publishes_result
    def sample_task():
        if exc:
            raise exc
        return "ok"

    return sample_task


def _published_statuses(mock_publish):
    return [c.kwargs.get("job_status") for c in mock_publish.call_args_list]


class TestFailureIsOnlyPublishedWhenRqGivesUp:
    def test_no_failed_event_while_retries_remain(self):
        import task as task_mod

        with (
            patch.object(
                task_mod, "get_current_job", return_value=_job(retries_left=2)
            ),
            patch.object(task_mod, "_publish_task_event") as pub,
        ):
            with pytest.raises(RuntimeError):
                _decorated(RuntimeError("transient"))()

        assert "failed" not in _published_statuses(pub)

    def test_failed_event_on_the_last_attempt(self):
        import task as task_mod

        with (
            patch.object(
                task_mod, "get_current_job", return_value=_job(retries_left=0)
            ),
            patch.object(task_mod, "_publish_task_event") as pub,
        ):
            with pytest.raises(RuntimeError):
                _decorated(RuntimeError("final"))()

        assert _published_statuses(pub) == ["failed"]

    def test_failed_event_when_the_task_has_no_retries_configured(self):
        import task as task_mod

        with (
            patch.object(
                task_mod, "get_current_job", return_value=_job(retries_left=None)
            ),
            patch.object(task_mod, "_publish_task_event") as pub,
        ):
            with pytest.raises(RuntimeError):
                _decorated(RuntimeError("boom"))()

        assert _published_statuses(pub) == ["failed"]

    def test_success_is_unaffected(self):
        import task as task_mod

        with (
            patch.object(
                task_mod, "get_current_job", return_value=_job(retries_left=2)
            ),
            patch.object(task_mod, "_publish_task_event") as pub,
        ):
            assert _decorated()() == "ok"

        assert _published_statuses(pub) == ["finished"]
