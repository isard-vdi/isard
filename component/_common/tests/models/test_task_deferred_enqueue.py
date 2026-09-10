# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin-down tests for ``Task``'s opt-in deferred enqueue (recycle-bin #2209).

``Task.__init__`` historically enqueued the RQ root job from *inside* the
constructor, so a worker could pick it up and finish before the caller had
finished its own bookkeeping. ``RecycleBin.delete_storage`` relied on that:
it created the ``delete`` Task and only afterwards registered it in the
entry's ``tasks`` array. A fast (file-absent / tiny-qcow2) delete could
therefore complete BEFORE registration, the completion signal was lost, and
the entry stayed ``deleting`` forever.

The structural fix gives ``Task`` an opt-in ``enqueue=False`` plus an
explicit ``.enqueue()`` so a caller can do
``create -> register -> enqueue`` and close the window: the worker can
never run before the task is registered.

These are *mechanics* tests (redis is mocked out) — they pin the enqueue
contract, not the race itself (the race needs the real stack).
"""

from unittest.mock import MagicMock, patch

from isardvdi_common.models.task import Task


def _build(**extra):
    """Run the real ``Task.__init__`` new-task path with ``Job``/``Queue``
    mocked so no redis is touched. Returns (task, Job, Queue, queue_obj, job)."""
    with patch("isardvdi_common.models.task.Job") as Job, patch(
        "isardvdi_common.models.task.Queue"
    ) as Queue:
        job = MagicMock(name="root_job")
        job.id = "root-1"
        job.meta = {}
        Job.create.return_value = job
        queue_obj = MagicMock(name="queue")
        queue_obj.enqueue_job.return_value = job
        Queue.return_value = queue_obj
        task = Task(task="delete", queue="storage.pool.default", **extra)
    return task, Job, Queue, queue_obj, job


def test_default_construction_enqueues_immediately():
    """Backward-compat: without the flag, the constructor still enqueues."""
    task, Job, Queue, queue_obj, job = _build()
    Job.create.assert_called_once()
    job.save.assert_called()
    Queue.assert_called_once_with("storage.pool.default", connection=Task._redis)
    queue_obj.enqueue_job.assert_called_once_with(job)


def test_enqueue_false_creates_and_saves_but_does_not_enqueue():
    """``enqueue=False`` creates + saves the job (id known, dependents deferred)
    but must NOT place it on the queue — this is the closed race window."""
    task, Job, Queue, queue_obj, job = _build(enqueue=False)
    Job.create.assert_called_once()
    job.save.assert_called()
    # The root job id exists (caller can register it) ...
    assert task.id == "root-1"
    # ... but nothing was enqueued.
    Queue.assert_not_called()
    queue_obj.enqueue_job.assert_not_called()


def test_explicit_enqueue_places_the_job_on_its_queue():
    """After a deferred construction, ``.enqueue()`` must enqueue exactly once
    on the ORIGINAL queue."""
    task, Job, Queue, queue_obj, job = _build(enqueue=False)
    with patch("isardvdi_common.models.task.Queue") as Queue2:
        q2 = MagicMock(name="queue2")
        q2.enqueue_job.return_value = job
        Queue2.return_value = q2
        ret = task.enqueue()
        Queue2.assert_called_once_with("storage.pool.default", connection=Task._redis)
        q2.enqueue_job.assert_called_once_with(job)
    assert ret is task  # chainable


def test_enqueue_is_idempotent():
    """A second ``.enqueue()`` is a no-op — never double-enqueue."""
    task, Job, Queue, queue_obj, job = _build(enqueue=False)
    with patch("isardvdi_common.models.task.Queue") as Queue2:
        q2 = MagicMock(name="queue2")
        q2.enqueue_job.return_value = job
        Queue2.return_value = q2
        task.enqueue()
        task.enqueue()
        q2.enqueue_job.assert_called_once()


def test_enqueue_noop_on_already_enqueued_default_task():
    """A task built the default (already-enqueued) way must treat a stray
    ``.enqueue()`` as a no-op, not a double enqueue."""
    task, Job, Queue, queue_obj, job = _build()  # enqueue=True path
    queue_obj.enqueue_job.reset_mock()
    with patch("isardvdi_common.models.task.Queue") as Queue2:
        q2 = MagicMock(name="queue2")
        Queue2.return_value = q2
        task.enqueue()
        q2.enqueue_job.assert_not_called()
