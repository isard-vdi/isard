# SPDX-License-Identifier: AGPL-3.0-or-later

"""The consumer's metadata finalize path.

A chain built in metadata mode carries its ``core`` finalize steps as
``meta["core_finalize"]`` on the root job, NOT as rq jobs. ``_process_entry``
must: run the same registered handlers, stamp each step's status IN the meta
(not via ``Job.set_status``), persist it with ``save_meta``, never call
``job.delete`` (there is no rq job), and enqueue a ``storage``-under-``core``
knot child as a fresh Task.
"""

import itertools
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rq.job import JobStatus

FIND_DEPENDENTS = [
    {
        "queue": "core",
        "task": "storage_update_pool",
        "job_kwargs": {"kwargs": {"storage_id": "s1"}},
        "dependents": [
            {
                "queue": "core",
                "task": "storage_update_parent",
                "job_kwargs": {"kwargs": {"storage_id": "s1"}},
            }
        ],
    }
]

KNOT_DEPENDENTS = [
    {
        "queue": "core",
        "task": "storage_update",
        "job_kwargs": {"kwargs": {"storage_id": "s1"}},
        "dependents": [
            {
                "queue": "storage.pool.default",
                "task": "qemu_img_info_backing_chain",
                "job_kwargs": {"kwargs": {"storage_id": "s2"}},
            }
        ],
    }
]


def _build_metadata_root(dependents):
    """A real metadata-mode root Task with Job/Queue mocked (no redis). Its
    ``job`` is a MagicMock whose ``meta`` holds the real ``core_finalize`` tree."""
    from isardvdi_common.models.task import Task

    ids = itertools.count(1)

    def make_job(*a, **k):
        job = MagicMock(name="job")
        job.id = f"job-{next(ids)}"
        job.meta = {}
        job.args = []
        job.get_position.return_value = None
        return job

    with patch("isardvdi_common.models.task.Job") as Job, patch(
        "isardvdi_common.models.task.Queue"
    ) as Queue:
        Job.create.side_effect = make_job
        q = MagicMock()
        q.enqueue_job.side_effect = lambda job: job
        Queue.return_value = q
        root = Task(
            task="find",
            queue="storage.pool.default",
            user_id="u1",
            dependents=dependents,
        )
    root.job.get_status.return_value = JobStatus.FINISHED
    return root


@pytest.mark.asyncio
async def test_metadata_finalize_runs_handlers_marks_and_persists():
    from isardvdi_change_handler.streams import task_results_consumer

    root = _build_metadata_root(FIND_DEPENDENTS)
    pool_handler = AsyncMock()
    parent_handler = MagicMock()
    registry = {
        "storage_update_pool": (pool_handler, True),
        "storage_update_parent": (parent_handler, False),
    }
    redis_manager = AsyncMock()
    with (
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.emit_task_feedback",
            new=AsyncMock(),
        ),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.Task",
            return_value=root,
        ),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.HANDLERS",
            registry,
        ),
    ):
        ok = await task_results_consumer._process_entry(
            redis_manager,
            {"kind": "result", "task_id": "job-1", "job_status": "finished"},
        )

    assert ok is True
    # both finalize handlers ran, receiving the CoreStep + its kwargs
    pool_handler.assert_awaited_once()
    assert pool_handler.await_args.kwargs == {"storage_id": "s1"}
    parent_handler.assert_called_once()
    # both meta nodes stamped finished, IN PLACE
    pool_node = root.job.meta["core_finalize"][0]
    assert pool_node["status"] == "finished"
    assert pool_node["core_finalize"][0]["status"] == "finished"
    # persisted, and NOT via the rq status path (no set_status on a step)
    root.job.save_meta.assert_called()


@pytest.mark.asyncio
async def test_metadata_finalize_does_not_delete_any_rq_job():
    """CoreSteps have no rq job; the cleanup loop must skip them (a MagicMock
    ``.job.delete`` would otherwise be called — assert it never is)."""
    from isardvdi_change_handler.streams import task_results_consumer

    root = _build_metadata_root(FIND_DEPENDENTS)
    registry = {
        "storage_update_pool": (AsyncMock(), True),
        "storage_update_parent": (MagicMock(), False),
    }
    with (
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.emit_task_feedback",
            new=AsyncMock(),
        ),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.Task",
            return_value=root,
        ),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.HANDLERS",
            registry,
        ),
    ):
        await task_results_consumer._process_entry(
            redis_manager=AsyncMock(),
            fields={"kind": "result", "task_id": "job-1", "job_status": "finished"},
        )
    # the only rq job in the chain is the root storage job; its delete is never
    # called by the finalize cleanup (only finalize steps are dropped, and those
    # aren't rq jobs in metadata mode).
    root.job.delete.assert_not_called()


@pytest.mark.asyncio
async def test_metadata_knot_enqueues_storage_child_as_fresh_task():
    from isardvdi_change_handler.streams import task_results_consumer

    root = _build_metadata_root(KNOT_DEPENDENTS)
    registry = {"storage_update": (AsyncMock(), True)}

    created = []

    def task_factory(*args, **kwargs):
        # id-hydration: Task("job-1") -> the root; knot enqueue: Task(**child)
        if args and not kwargs:
            return root
        created.append(kwargs)
        return MagicMock()

    task_mock = MagicMock(side_effect=task_factory)
    task_mock.exists.return_value = False  # not yet enqueued

    with (
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.emit_task_feedback",
            new=AsyncMock(),
        ),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.Task",
            task_mock,
        ),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.HANDLERS",
            registry,
        ),
    ):
        await task_results_consumer._process_entry(
            redis_manager=AsyncMock(),
            fields={"kind": "result", "task_id": "job-1", "job_status": "finished"},
        )

    assert len(created) == 1
    knot = created[0]
    assert knot["task"] == "qemu_img_info_backing_chain"
    assert knot["queue"] == "storage.pool.default"
    # deterministic id so a redelivery is a no-op (guarded by Task.exists)
    assert knot["job_kwargs"]["id"].endswith(":sd:0")


@pytest.mark.asyncio
async def test_metadata_knot_skipped_when_already_enqueued():
    """Idempotency: if the knot child already exists (redelivery), do not
    enqueue it again."""
    from isardvdi_change_handler.streams import task_results_consumer

    root = _build_metadata_root(KNOT_DEPENDENTS)
    registry = {"storage_update": (AsyncMock(), True)}
    created = []

    def task_factory(*args, **kwargs):
        if args and not kwargs:
            return root
        created.append(kwargs)
        return MagicMock()

    task_mock = MagicMock(side_effect=task_factory)
    task_mock.exists.return_value = True  # already there

    with (
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.emit_task_feedback",
            new=AsyncMock(),
        ),
        patch("isardvdi_change_handler.streams.task_results_consumer.Task", task_mock),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.HANDLERS", registry
        ),
    ):
        await task_results_consumer._process_entry(
            redis_manager=AsyncMock(),
            fields={"kind": "result", "task_id": "job-1", "job_status": "finished"},
        )
    assert created == []


@pytest.mark.asyncio
async def test_metadata_failed_chain_marks_failed_and_does_not_enqueue_knot():
    """A failed chain still runs the finalize handlers (to release the row) but
    marks each step failed and does NOT advance a storage-under-core knot."""
    from isardvdi_change_handler.streams import task_results_consumer

    root = _build_metadata_root(KNOT_DEPENDENTS)
    handler = AsyncMock()
    registry = {"storage_update": (handler, True)}
    created = []

    def task_factory(*args, **kwargs):
        if args and not kwargs:
            return root
        created.append(kwargs)
        return MagicMock()

    task_mock = MagicMock(side_effect=task_factory)
    task_mock.exists.return_value = False

    with (
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.emit_task_feedback",
            new=AsyncMock(),
        ),
        patch("isardvdi_change_handler.streams.task_results_consumer.Task", task_mock),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.HANDLERS", registry
        ),
    ):
        await task_results_consumer._process_entry(
            redis_manager=AsyncMock(),
            fields={"kind": "result", "task_id": "job-1", "job_status": "failed"},
        )

    # the finalize handler still ran (releases the row)...
    handler.assert_awaited_once()
    # ...the step is marked failed, not finished...
    assert root.job.meta["core_finalize"][0]["status"] == "failed"
    # ...and the knot storage child is NOT enqueued (failure must not advance).
    assert created == []


@pytest.mark.asyncio
async def test_metadata_handler_raise_on_finished_chain_marks_failed_and_nacks():
    """A finalize handler that RAISES on an otherwise-successful chain
    (job_status='finished') must mark its step failed (NOT finished), NOT advance
    the knot, and make _process_entry return False so the entry is not ACKed and
    is redelivered — the load-bearing at-least-once contract."""
    from isardvdi_change_handler.streams import task_results_consumer

    root = _build_metadata_root(KNOT_DEPENDENTS)
    handler = AsyncMock(side_effect=RuntimeError("boom"))
    registry = {"storage_update": (handler, True)}
    created = []

    def task_factory(*args, **kwargs):
        if args and not kwargs:
            return root
        created.append(kwargs)
        return MagicMock()

    task_mock = MagicMock(side_effect=task_factory)
    task_mock.exists.return_value = False

    with (
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.emit_task_feedback",
            new=AsyncMock(),
        ),
        patch("isardvdi_change_handler.streams.task_results_consumer.Task", task_mock),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.HANDLERS", registry
        ),
    ):
        ok = await task_results_consumer._process_entry(
            redis_manager=AsyncMock(),
            fields={"kind": "result", "task_id": "job-1", "job_status": "finished"},
        )

    assert ok is False  # not ACKed -> redelivered
    assert root.job.meta["core_finalize"][0]["status"] == "failed"
    assert created == []  # knot not advanced on a raised handler
