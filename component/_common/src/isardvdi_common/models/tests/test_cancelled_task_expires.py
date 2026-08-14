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
"""A cancelled task expires like any other terminal one.

rq expires a job's keys from exactly one place — ``Job.cleanup(ttl=...)`` — and
the only callers are the worker's success and failure handlers. ``Job.cancel``
is not one of them: it moves the job into ``CanceledJobRegistry`` and stops. So
a member cancelled *before* a worker dequeued it keeps its hash with no expiry,
and nothing sweeps it afterwards — ``CanceledJobRegistry`` inherits the no-op
``BaseRegistry.cleanup``, and the operator reaper is opt-in (a fresh
``populate`` writes no ``old_tasks`` config) and defaults to ``finished`` only.

Measured on a clean install through ``DELETE /api/v4/admin/task/{id}``, which is
the control group these tests encode: a member a worker had already dequeued ends
``failed`` with a 30-day TTL, while a member still QUEUED ends ``canceled`` with
TTL -1. Same registry, same operation; only the second one is immortal.
"""

import os
from unittest.mock import MagicMock, patch

from isardvdi_common.models.task import (
    _EXPIRE_IF_UNSET,
    _stamp_expiry,
    task_retention_seconds,
)

DEFAULT_RETENTION = 2592000
JOB_ID = "0e8acd36-0f7b-44bb-acde-7b30f587e02a"


def _expiry_calls(job_id=JOB_ID, env=None):
    """Run ``_stamp_expiry`` against a fake redis and return its eval calls."""
    connection = MagicMock(name="redis")
    with patch.dict(os.environ, env or {}, clear=False):
        _stamp_expiry(connection, job_id)
    return connection.eval.call_args_list


def test_every_key_rq_would_have_expired_is_expired():
    """``Job.cleanup`` expires the hash and both edge keys. A cancel has to
    leave the same set behind, or the chain outlives the job it belonged to.

    ``Job.key_for`` hands back bytes while the dependencies key is built as a
    str; redis takes either, so the comparison normalises rather than pinning
    a type the caller does not depend on."""
    keys = [
        k.decode() if isinstance(k, bytes) else k
        for k in (call.args[2] for call in _expiry_calls())
    ]

    assert keys == [
        f"rq:job:{JOB_ID}",
        f"rq:job:{JOB_ID}:dependents",
        # rq spells this one with a double colon; see ``_stamp_expiry``.
        f"rq:job::{JOB_ID}:dependencies",
    ]


def test_the_clock_is_the_one_a_finished_task_gets():
    """A cancel must not invent a retention of its own: the whole point is that
    it stops being the one terminal state with no clock."""
    for call in _expiry_calls():
        assert call.args[3] == DEFAULT_RETENTION


def test_the_deployment_can_still_set_the_retention():
    """``REDIS_TASK_RESULT_TTL`` governs creation, so it has to govern the
    cancel too — otherwise an install that shortens retention keeps its
    cancelled tasks for thirty days regardless."""
    for call in _expiry_calls(env={"REDIS_TASK_RESULT_TTL": "600"}):
        assert call.args[3] == 600


def test_an_unreadable_retention_falls_back_instead_of_raising():
    """A bad value in the environment must not turn a cancel into an
    exception: the cancel is the user-visible operation, the expiry is
    bookkeeping attached to it."""
    assert task_retention_seconds() == DEFAULT_RETENTION
    with patch.dict(os.environ, {"REDIS_TASK_RESULT_TTL": "not-a-number"}):
        assert task_retention_seconds() == DEFAULT_RETENTION
    with patch.dict(os.environ, {"REDIS_TASK_RESULT_TTL": ""}):
        assert task_retention_seconds() == DEFAULT_RETENTION


def test_a_redis_that_refuses_does_not_break_the_cancel():
    """Best-effort, like every other stamp on this path. A cancel that raises
    because it could not write a TTL has failed at the thing the user asked
    for in order to succeed at the thing they did not."""
    connection = MagicMock(name="redis")
    connection.eval.side_effect = Exception("redis is unreachable")

    _stamp_expiry(connection, JOB_ID)  # must not raise

    assert connection.eval.call_count == 3


def test_the_script_only_stamps_a_key_that_has_no_clock_yet():
    """The guard is what makes this safe to run over a whole chain: a member a
    worker had already dequeued gets its expiry from rq's failure handler, and
    re-stamping it would move that deadline. It also makes a second cancel of
    the same chain a no-op."""
    assert "EXISTS" in _EXPIRE_IF_UNSET
    assert "TTL" in _EXPIRE_IF_UNSET
    assert "== -1" in _EXPIRE_IF_UNSET
