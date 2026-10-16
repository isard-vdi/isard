# SPDX-License-Identifier: AGPL-3.0-or-later

"""The old-tasks sweep removes a job's result stream along with the job."""

from unittest.mock import MagicMock

from api.services.admin.queues import AdminQueuesService


def _job(job_id, delete_raises=False):
    job = MagicMock()
    job.id = job_id
    job.connection = MagicMock()
    if delete_raises:
        job.delete.side_effect = RuntimeError("redis gone")
    return job


def test_a_swept_job_takes_its_results_with_it():
    job = _job("j-1")

    ok, errors = AdminQueuesService._delete_jobs([job])

    assert (ok, errors) == (["j-1"], [])
    job.delete.assert_called_once_with(delete_dependents=True)
    job.connection.delete.assert_called_once_with("rq:results:j-1")


def test_a_job_that_could_not_be_deleted_keeps_its_results():
    job = _job("j-2", delete_raises=True)

    ok, errors = AdminQueuesService._delete_jobs([job])

    assert (ok, errors) == ([], ["j-2"])
    job.connection.delete.assert_not_called()
