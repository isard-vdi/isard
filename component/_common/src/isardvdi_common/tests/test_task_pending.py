# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``Task.pending`` orphan-awareness and ``Task.chain_pending``.

A storage keeps the id of the last task that operated on it in
``storage.task`` and that reference is never cleared. If that task's chain
contains a ``DEFERRED`` job that was orphaned (its finalize crashed, so it was
never re-enqueued), the storage would otherwise look "pending" forever and
block every future operation with a false 428 ``storage_pending_task`` (e.g.
converting a desktop to a template). ``pending`` must distinguish a genuinely
waiting ``DEFERRED`` job from an orphaned one.
"""

from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

import pytest
from isardvdi_common.models import task as task_module
from isardvdi_common.models.task import Task
from rq.job import JobStatus


def _member(job_status, depending_status=JobStatus.FINISHED):
    return SimpleNamespace(job_status=job_status, depending_status=depending_status)


def _pending_for_chain(chain):
    task = object.__new__(Task)  # skip __init__ (no redis needed)
    with patch.object(Task, "_chain", new_callable=PropertyMock, return_value=chain):
        return task.pending


def test_pending_false_when_whole_chain_finished():
    chain = [_member(JobStatus.FINISHED), _member(JobStatus.FINISHED)]
    assert _pending_for_chain(chain) is False


def test_pending_true_when_a_job_is_started():
    chain = [_member(JobStatus.FINISHED), _member(JobStatus.STARTED)]
    assert _pending_for_chain(chain) is True


def test_pending_true_for_deferred_job_still_waiting_on_a_dependency():
    # legitimate in-flight chain: dependent DEFERRED while its dependency runs
    chain = [_member(JobStatus.DEFERRED, depending_status=JobStatus.STARTED)]
    assert _pending_for_chain(chain) is True


def test_pending_false_for_orphaned_deferred_dependent():
    # the bug: root FINISHED, dependent DEFERRED but its deps all finished ->
    # never re-enqueued -> orphan -> must NOT block.
    chain = [
        _member(JobStatus.FINISHED),
        _member(JobStatus.DEFERRED, depending_status=JobStatus.FINISHED),
    ]
    assert _pending_for_chain(chain) is False


# ---------------------------------------------------------------------------
# ``chain_pending`` — the same question asked of the WHOLE chain
#
# ``pending`` reads ``dependencies + self + dependents``, and ``dependents``
# lists direct children only. Anything deeper reads as settled from the root
# while a worker is still writing, which is what a caller deciding "may I act
# on this disk?" must never be told.
# ---------------------------------------------------------------------------


class _Job:
    """An rq job as ``_chain_closure`` walks it: an id, a status and meta."""

    def __init__(self, job_id, status, dependency_ids=(), dependent_ids=()):
        self.id = job_id
        self._status = status
        self.meta = {
            "dependency_ids": list(dependency_ids),
            "dependent_ids": list(dependent_ids),
        }

    def get_status(self, refresh=True):
        return self._status


def _chain_pending_for(jobs):
    """``chain_pending`` over ``jobs``, the first being the chain's root."""
    by_id = {job.id: job for job in jobs}
    task = object.__new__(Task)  # skip __init__ (no real redis needed)
    task.job = jobs[0]
    task._redis = object()
    with patch.object(
        task_module.Job,
        "fetch",
        side_effect=lambda job_id, connection=None: by_id[job_id],
    ):
        return task.chain_pending


def test_chain_pending_sees_work_deeper_than_the_immediate_neighbours():
    # root -> child -> grandchild: the depth a template creation reaches. The
    # first two levels are done, so the root's own chain looks settled while
    # the grandchild is still writing the disk.
    jobs = [
        _Job("root", JobStatus.FINISHED, dependent_ids=["child"]),
        _Job(
            "child",
            JobStatus.FINISHED,
            dependency_ids=["root"],
            dependent_ids=["grandchild"],
        ),
        _Job("grandchild", JobStatus.STARTED, dependency_ids=["child"]),
    ]
    assert _chain_pending_for(jobs) is True


def test_chain_pending_false_when_the_whole_closure_settled():
    jobs = [
        _Job("root", JobStatus.FINISHED, dependent_ids=["child"]),
        _Job(
            "child",
            JobStatus.FINISHED,
            dependency_ids=["root"],
            dependent_ids=["grandchild"],
        ),
        _Job("grandchild", JobStatus.FINISHED, dependency_ids=["child"]),
    ]
    assert _chain_pending_for(jobs) is False


def test_chain_pending_true_for_a_deferred_member_still_waiting():
    jobs = [
        _Job("root", JobStatus.STARTED, dependent_ids=["child"]),
        _Job("child", JobStatus.DEFERRED, dependency_ids=["root"]),
    ]
    assert _chain_pending_for(jobs) is True


def test_chain_pending_false_for_an_orphaned_deferred_member():
    # Same orphan rule as ``pending``: a DEFERRED whose dependencies have all
    # settled was never re-enqueued and must not block for ever.
    jobs = [
        _Job("root", JobStatus.FINISHED, dependent_ids=["child"]),
        _Job("child", JobStatus.DEFERRED, dependency_ids=["root"]),
    ]
    assert _chain_pending_for(jobs) is False


@pytest.mark.parametrize(
    "failure",
    ["closure", "status"],
    ids=["chain unreadable", "member status unreadable"],
)
def test_chain_pending_true_when_the_chain_cannot_be_read(failure):
    # Not being able to prove the work is over is not the same as it being
    # over: answer "still busy" and let the next sweep decide.
    task = object.__new__(Task)
    task.job = _Job("root", JobStatus.FINISHED)
    task._redis = object()
    if failure == "closure":
        with patch.object(task_module, "_chain_closure", side_effect=Exception):
            assert task.chain_pending is True
    else:
        with patch.object(_Job, "get_status", side_effect=Exception), patch.object(
            task_module, "_chain_closure", return_value={"root": task.job}
        ):
            assert task.chain_pending is True
