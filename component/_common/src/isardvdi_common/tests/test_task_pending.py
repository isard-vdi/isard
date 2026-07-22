# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``Task.pending`` orphan-awareness.

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
