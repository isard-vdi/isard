# SPDX-License-Identifier: AGPL-3.0-or-later

"""Deciding whether a download was cancelled, without a database to ask.

The check used to read the row's status and answer *"yes, abort"* to any
failure of that lookup. On a node with no ``isard-db`` — the normal state for
the storage, hypervisor and hypervisor-standalone flavours — the lookup always
fails, so curl was killed before its first byte, the partial file was unlinked
and the job raised ``CalledProcessError(130)``: every download on every remote
node failed, and failed looking exactly like a user cancelling it.

The signal is now the job's own status, which lives in redis. ``Task.cancel``
sets it persistently, so it also closes the race the row lookup covered: a
cancel published before the watcher subscribed is still visible on entry.
"""

from unittest.mock import MagicMock

import pytest
from rq.job import JobStatus


@pytest.fixture
def job(monkeypatch):
    import task

    j = MagicMock()
    monkeypatch.setattr(task, "get_current_job", lambda: j, raising=False)
    return j


def test_a_cancelled_job_aborts(job):
    import task

    job.get_status.return_value = JobStatus.CANCELED

    assert task._job_canceled() is True


@pytest.mark.parametrize(
    "status", [JobStatus.STARTED, JobStatus.QUEUED, JobStatus.DEFERRED]
)
def test_a_running_job_is_left_alone(job, status):
    import task

    job.get_status.return_value = status

    assert task._job_canceled() is False


def test_the_status_is_read_fresh(job):
    """A cached status would miss a cancel that arrived after the job started."""
    import task

    job.get_status.return_value = JobStatus.STARTED
    task._job_canceled()

    job.get_status.assert_called_once_with(refresh=True)


def test_an_unreachable_redis_does_not_abort_the_download(job):
    """Fail open: losing the cancel channel must not kill a live transfer."""
    import task

    job.get_status.side_effect = RuntimeError("no redis")

    assert task._job_canceled() is False


def test_no_job_means_nothing_to_cancel(monkeypatch):
    import task

    monkeypatch.setattr(task, "get_current_job", lambda: None, raising=False)

    assert task._job_canceled() is False


def test_the_progress_is_stated_in_the_job_metadata(job):
    """The worker states the row progress; change-handler persists it."""
    import task

    job.meta = {}
    payload = {"received_percent": 42, "total_percent": 42}

    task._state_progress(payload)

    assert job.meta[task.ROW_PROGRESS_META_KEY] == payload
    job.save_meta.assert_called_once()


def test_stating_progress_outside_a_job_is_harmless(monkeypatch):
    import task

    monkeypatch.setattr(task, "get_current_job", lambda: None, raising=False)

    task._state_progress({"received_percent": 1})
