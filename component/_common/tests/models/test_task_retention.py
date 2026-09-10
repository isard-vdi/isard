#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 Josep Maria Viñolas Auquer
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""A task is retained for the same time whether it succeeds or fails.

rq writes the failure result to its own stream and only EXPIREs it when a
``failure_ttl`` is given, so leaving it unset means the successful path expires
after ``result_ttl`` while the failed one never does — unbounded growth on the
only path that purely accumulates.
"""

import os
from unittest.mock import MagicMock, patch

from isardvdi_common.models.task import Task

DEFAULT_RETENTION = 2592000


def _job_kwargs_of_a_new_task(env=None, job_kwargs=None):
    """Create a Task and return the kwargs it handed to ``Job.create``."""
    with patch.dict(os.environ, env or {}, clear=False), patch(
        "isardvdi_common.models.task.Job"
    ) as Job, patch("isardvdi_common.models.task.Queue") as Queue:
        job = MagicMock(name="job")
        job.id = "root-1"
        job.meta = {}
        Job.create.return_value = job
        Queue.return_value.enqueue_job.return_value = job
        Task(
            task="delete",
            user_id="u",
            queue="storage.default.default.maintenance",
            job_kwargs=dict(job_kwargs or {}),
        )
        return Job.create.call_args.kwargs


def test_failure_and_result_share_one_retention():
    kwargs = _job_kwargs_of_a_new_task()
    assert kwargs["failure_ttl"] == kwargs["result_ttl"] == DEFAULT_RETENTION


def test_the_installation_setting_governs_both():
    """The value is normalised to an int. It used to be passed through as the
    raw string when the variable was set, while the default was an int — so the
    type of one retention depended on whether the deployment had overridden it,
    and a cancel now reads the same setting to expire its own keys."""
    kwargs = _job_kwargs_of_a_new_task({"REDIS_TASK_RESULT_TTL": "600"})
    assert kwargs["failure_ttl"] == kwargs["result_ttl"] == 600


def test_an_explicit_failure_ttl_is_respected():
    """``setdefault``, not an override: a caller that knows better keeps it."""
    kwargs = _job_kwargs_of_a_new_task(job_kwargs={"failure_ttl": 42})
    assert kwargs["failure_ttl"] == 42
    assert kwargs["result_ttl"] == DEFAULT_RETENTION
