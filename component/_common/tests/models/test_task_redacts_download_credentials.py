# SPDX-License-Identifier: AGPL-3.0-or-later

"""A registry download carries the registration code in an ``Authorization``
header. It must reach the worker, and nothing that is logged or serialised.
"""

from unittest.mock import MagicMock, patch

from isardvdi_common.models.task import Task, redact_task_kwargs

SECRET = "registration-code-1234"
DOWNLOAD_KWARGS = {
    "domain_id": "d1",
    "storage_id": "s1",
    "url": "https://registry.example/storage/domains/x.qcow2",
    "dest_path": "/isard/x.qcow2",
    "headers": [f"Authorization: {SECRET}"],
    "insecure_ssl": False,
    "google_drive_cookie": None,
}


def _create(call_kwargs):
    with patch("isardvdi_common.models.task.Job") as Job, patch(
        "isardvdi_common.models.task.Queue"
    ) as Queue:
        job = MagicMock(name="job")
        job.id = "root-1"
        job.meta = {}
        job.args = []
        job.kwargs = call_kwargs
        job.get_position.return_value = None
        Job.create.return_value = job
        Queue.return_value.enqueue_job.return_value = job
        task = Task(
            task="download_url_for_domain",
            user_id="u",
            queue="storage.default.low",
            job_kwargs={"kwargs": dict(call_kwargs)},
        )
        return task, Job.create.call_args.kwargs


def test_the_worker_still_receives_the_real_header():
    _, created = _create(DOWNLOAD_KWARGS)

    assert created["kwargs"]["headers"] == [f"Authorization: {SECRET}"]


def test_the_logged_description_does_not_carry_the_code():
    _, created = _create(DOWNLOAD_KWARGS)

    assert SECRET not in created["description"]
    assert "download_url_for_domain" in created["description"]
    assert "Authorization: ***" in created["description"]


def test_the_serialised_task_does_not_carry_the_code():
    task, _ = _create(DOWNLOAD_KWARGS)

    data = task.to_dict()

    assert SECRET not in repr(data)
    assert data["kwargs"]["headers"] == ["Authorization: ***"]
    assert data["kwargs"]["url"] == DOWNLOAD_KWARGS["url"]


def test_a_task_without_credentials_keeps_rq_default_description():
    _, created = _create({"storage_id": "s1", "headers": []})

    assert "description" not in created


def test_a_google_drive_cookie_is_masked_too():
    assert redact_task_kwargs({"google_drive_cookie": "abc"}) == {
        "google_drive_cookie": "***"
    }
