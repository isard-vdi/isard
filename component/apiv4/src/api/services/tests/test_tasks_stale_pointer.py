#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Every ``TaskService`` entry point must survive a task id whose RQ job is
gone.

All four paired ``Task.exists`` / ``Task(task_id)`` sites had the same two
defects. The check is a bare key check, so a hash left with just a status field
— a job deleted while something was still writing it — passes and then cannot
be loaded; and check-then-construct is a race, so even a sound check can be
stale by the time the construct runs. Either way ``NoSuchJobError`` escapes the
service and the route turns it into a 500, where "there is no such task" (404)
was available all along.

Each test leaves the job hash present but unloadable, which is exactly the
shape the key check waves through.
"""

from unittest.mock import patch

import pytest
from api.services.error import Error
from api.services.tasks import TaskService
from rq.exceptions import NoSuchJobError

OWNER = "u-1"


def _unloadable_job():
    """``exists`` says the hash is there; ``fetch`` cannot load it."""
    return patch("isardvdi_common.models.task.Job.exists", return_value=True), patch(
        "isardvdi_common.models.task.Job.fetch",
        side_effect=NoSuchJobError("No such job: t-gone"),
    )


@pytest.mark.parametrize(
    ("name", "call"),
    [
        ("get_task", lambda: TaskService.get_task("t-gone")),
        (
            "get_task_with_owner_check",
            lambda: TaskService.get_task_with_owner_check("t-gone", OWNER, "user"),
        ),
        (
            "get_task_details_with_owner_check",
            lambda: TaskService.get_task_details_with_owner_check(
                "t-gone", OWNER, "user"
            ),
        ),
        ("retry_task", lambda: TaskService.retry_task("t-gone")),
        ("admin_cancel_task", lambda: TaskService.admin_cancel_task("t-gone")),
    ],
)
def test_unloadable_task_is_not_found_not_a_crash(name, call):
    exists, fetch = _unloadable_job()
    with exists, fetch:
        with pytest.raises(Error) as excinfo:
            call()
    assert excinfo.value.status_code == 404, name
