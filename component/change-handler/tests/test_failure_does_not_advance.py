# SPDX-License-Identifier: AGPL-3.0-or-later

"""A chain that failed must not advance past its failure.

The finalize handlers are gated on `depending_status`: when the chain failed
they no-op and return without raising, which the consumer scored as success. It
then marked that step FINISHED and released its deferred storage dependents, so
the next stage ran against work its parent never produced - and a nested core
step read `depending_status == "finished"` and took its success body for an
operation that never happened.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from isardvdi_common.models.task import CoreStep
from rq.job import JobStatus


def _core_step(
    node_id,
    task_name="storage_update",
    kwargs=None,
    storage_dependents=None,
    parent_status=JobStatus.FINISHED,
):
    """A real metadata finalize step (the only kind the consumer dispatches).
    Its parent is terminal so the step is QUEUED (dispatchable)."""
    node = {
        "id": node_id,
        "task": task_name,
        "queue": "core",
        "kwargs": kwargs or {},
        "args": [],
        "core_finalize": [],
        "storage_dependents": storage_dependents or [],
        "status": None,
    }
    # The parent stands in for the step's ANCHOR: the real rq job whose meta
    # carries this node, and where the consumer makes the step's mark durable.
    # It therefore needs an id and a job, like the Task it doubles for.
    anchor = SimpleNamespace(
        job_status=parent_status, id=f"anchor-of-{node_id}", job=MagicMock()
    )
    return CoreStep(node, anchor, MagicMock())


def _stub(
    task_id,
    *,
    task_name="storage_update",
    queue="core",
    dependents=None,
    job_status=JobStatus.DEFERRED,
):
    job = MagicMock(name=f"job-{task_id}")
    job.get_status.return_value = job_status
    return SimpleNamespace(
        id=task_id,
        task=task_name,
        queue=queue,
        depending_status="failed",
        kwargs={},
        dependents=dependents or [],
        job=job,
        job_status=job_status,
        # No cancel record on this member. A bare MagicMock would answer
        # every hget truthily, i.e. "cancelled", which is the one thing a
        # default must never mean.
        _redis=MagicMock(**{"hget.return_value": None}),
    )


def _patches(root, handlers):
    return (
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.emit_task_feedback",
            new=AsyncMock(),
        ),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.Task",
            return_value=root,
        ),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.HANDLERS", handlers
        ),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer._stamp_ended_at",
            MagicMock(),
        ),
    )


class TestFailedChainDoesNotAdvance:
    @pytest.mark.asyncio
    async def test_storage_dependents_are_not_released(self):
        """The damage: the next storage stage running against a disk its
        parent never wrote."""
        from isardvdi_change_handler.streams import task_results_consumer

        dep = _core_step("dep")
        root = _stub(
            "root",
            task_name="create",
            queue="storage.pool.interactive",
            dependents=[dep],
        )
        e, t, h, st = _patches(root, {"storage_update": (AsyncMock(), True)})

        with e, t, h, st, patch(
            "isardvdi_change_handler.streams.task_results_consumer._enqueue_metadata_storage_dependents",
            new=AsyncMock(),
        ) as enqueue:
            await task_results_consumer._process_entry(
                AsyncMock(),
                {"kind": "result", "task_id": "root", "job_status": "failed"},
            )

        enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_no_op_step_is_not_marked_finished(self):
        """Marking it FINISHED is what makes a NESTED step read
        ``depending_status == "finished"`` and run its success body."""
        from isardvdi_change_handler.streams import task_results_consumer

        # The step hangs off the root the event says FAILED, so that is what
        # its own dependency status has to report.
        dep = _core_step("dep", parent_status=JobStatus.FAILED)
        root = _stub(
            "root",
            task_name="create",
            queue="storage.pool.interactive",
            dependents=[dep],
        )
        e, t, h, st = _patches(root, {"storage_update": (AsyncMock(), True)})

        with e, t, h, st, patch(
            "isardvdi_change_handler.streams.task_results_consumer._enqueue_metadata_storage_dependents",
            new=AsyncMock(),
        ):
            await task_results_consumer._process_entry(
                AsyncMock(),
                {"kind": "result", "task_id": "root", "job_status": "failed"},
            )

        assert dep._node["status"] == "failed"


class TestSuccessfulChainStillAdvances:
    @pytest.mark.asyncio
    async def test_release_and_finished_still_happen(self):
        from isardvdi_change_handler.streams import task_results_consumer

        dep = _core_step("dep")
        root = _stub(
            "root",
            task_name="create",
            queue="storage.pool.interactive",
            dependents=[dep],
        )
        e, t, h, st = _patches(root, {"storage_update": (AsyncMock(), True)})

        with e, t, h, st, patch(
            "isardvdi_change_handler.streams.task_results_consumer._enqueue_metadata_storage_dependents",
            new=AsyncMock(),
        ) as enqueue:
            await task_results_consumer._process_entry(
                AsyncMock(),
                {"kind": "result", "task_id": "root", "job_status": "finished"},
            )

        assert dep._node["status"] == "finished"
        enqueue.assert_awaited_once()


class TestSettledStepsAreAgeable:
    @pytest.mark.asyncio
    async def test_marking_a_step_also_stamps_its_end_time(self):
        """``set_status`` writes one field, so without this a storage job
        stranded behind a settled core step is invisible to the orphan pass."""
        from isardvdi_change_handler.streams import task_results_consumer

        dep = _stub("dep")

        with patch(
            "isardvdi_change_handler.streams.task_results_consumer._stamp_ended_at"
        ) as stamp:
            await task_results_consumer._set_job_status(dep, JobStatus.FINISHED)

        stamp.assert_called_once()


class TestPerStepOutcome:
    """A finalize step's outcome is its own, not the chain's.

    A chain cancelled half way still contains steps whose dependency genuinely
    succeeded. Marking those FAILED because the chain as a whole did not
    succeed rewrites history that happened, and tells the step below them that
    a dependency failed when it did not.
    """

    @pytest.mark.asyncio
    async def test_a_step_whose_dependency_succeeded_is_marked_finished(self):
        from isardvdi_change_handler.streams import task_results_consumer

        step = _core_step("succeeded-step")  # parent is FINISHED
        root = _stub(
            "root",
            queue="storage.pool.template",
            dependents=[step],
            job_status=JobStatus.CANCELED,
        )

        with (
            patch.object(task_results_consumer, "emit_task_feedback", new=AsyncMock()),
            patch.object(task_results_consumer, "HANDLERS", {}),
            patch.object(task_results_consumer, "Task", return_value=root),
        ):
            await task_results_consumer._process_entry(
                AsyncMock(),
                {"kind": "canceled", "task_id": "root", "job_status": "canceled"},
            )

        assert step.job_status == JobStatus.FINISHED

    @pytest.mark.asyncio
    async def test_a_step_whose_dependency_was_cancelled_is_marked_failed(self):
        from isardvdi_change_handler.streams import task_results_consumer

        step = CoreStep(
            {
                "id": "cancelled-dep-step",
                "task": "storage_update",
                "queue": "core",
                "kwargs": {},
                "args": [],
                "core_finalize": [],
                "storage_dependents": [],
                "status": None,
            },
            SimpleNamespace(
                job_status=JobStatus.CANCELED, id="anchor", job=MagicMock()
            ),
            MagicMock(),
        )
        root = _stub(
            "root",
            queue="storage.pool.template",
            dependents=[step],
            job_status=JobStatus.CANCELED,
        )

        with (
            patch.object(task_results_consumer, "emit_task_feedback", new=AsyncMock()),
            patch.object(task_results_consumer, "HANDLERS", {}),
            patch.object(task_results_consumer, "Task", return_value=root),
        ):
            await task_results_consumer._process_entry(
                AsyncMock(),
                {"kind": "canceled", "task_id": "root", "job_status": "canceled"},
            )

        assert step.job_status == JobStatus.FAILED
