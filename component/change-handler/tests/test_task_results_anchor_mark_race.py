# SPDX-License-Identifier: AGPL-3.0-or-later

"""A dispatch must not lose the finalize marks a concurrent dispatch made.

Every mark a dispatch writes lands in the ``meta`` of the rq job carrying the
finalize tree, and ``save_meta`` writes that whole blob back. Two dispatches
that reach one anchor each hydrate their own copy of it, so the one that saves
second overwrites whatever the first wrote.

The two events here are the ordinary shape of that: on a chain whose members
have settled, a ``failed`` result walks through them and reaches the finalize
steps of the knot child that will now never be built, while a ``finished``
result on the anchor itself reaches only the steps hanging directly off it.
Different step sets, one anchor.
"""

import asyncio
import contextvars
import time
from unittest.mock import AsyncMock, patch

import pytest
from isardvdi_common.models.task import Task
from rq.job import Job, JobStatus

from ._chain_harness import repair_storage_new_slot  # noqa: F401  (fixture)
from ._chain_harness import (
    finalize_nodes,
    recording_handlers,
    storage_jobs,
    template_chain_kwargs,
)

# A ContextVar because ``asyncio.to_thread`` carries the calling task's
# context, so each dispatch's own delay reaches its own save.
_SAVE_DELAY = contextvars.ContextVar("save_delay", default=0.0)


def _result_event(job, job_status):
    return {
        "kind": "result",
        "task_id": job.id,
        "task_name": str(job.func_name).rsplit(".", 1)[-1],
        "queue": job.origin,
        "job_status": job_status,
    }


def _persisted_marks(connection):
    marks = {}
    for job_id in storage_jobs(connection):
        for node in finalize_nodes(Job.fetch(job_id, connection=connection)):
            marks[node["id"]] = node.get("status")
    return marks


@pytest.mark.asyncio
async def test_a_second_dispatch_does_not_erase_the_first_s_marks(
    task_on_scratch_redis, repair_storage_new_slot  # noqa: F811
):
    from isardvdi_change_handler.streams import task_results_consumer

    root = Task(**template_chain_kwargs())
    jobs = storage_jobs(task_on_scratch_redis)
    anchor_id = next(
        job_id for job_id, job in jobs.items() if (job.meta or {}).get("core_finalize")
    )
    # A walk crosses a storage member only once it will never run again, so
    # settle them: this is the dead chain both events arrive on.
    for job_id in jobs:
        Job.fetch(job_id, connection=task_on_scratch_redis).set_status(JobStatus.FAILED)

    ran = []
    real_save_meta = Job.save_meta

    def delayed_save_meta(self):
        time.sleep(_SAVE_DELAY.get())
        real_save_meta(self)

    async def dispatch(event, save_delay, start_delay=0.0):
        _SAVE_DELAY.set(save_delay)
        await asyncio.sleep(start_delay)
        return await task_results_consumer._process_entry(AsyncMock(), event)

    with (
        patch.object(task_results_consumer, "emit_task_feedback", new=AsyncMock()),
        patch.object(task_results_consumer, "handle_row_progress", new=AsyncMock()),
        patch.object(
            task_results_consumer,
            "_enqueue_metadata_storage_dependents",
            new=AsyncMock(return_value=True),
        ),
        patch.object(task_results_consumer, "HANDLERS", recording_handlers(ran)),
        patch.object(Job, "save_meta", delayed_save_meta),
    ):
        # The finished leg follows while the failed one is still saving: late
        # enough to queue behind it, early enough for a lock-free read to be stale.
        await asyncio.gather(
            dispatch(_result_event(jobs[root.id], "failed"), 0.2),
            dispatch(_result_event(jobs[anchor_id], "finished"), 0.5, 0.05),
        )

    dispatched = sorted({step_id for _name, step_id, _kwargs in ran})
    assert [step for step in dispatched if "-sd-" in step], (
        "the failed leg never reached the unbuilt knot steps, so the two "
        f"dispatches did not overlap on one anchor: {dispatched}"
    )

    marks = _persisted_marks(task_on_scratch_redis)
    lost = [step for step in dispatched if marks.get(step) is None]
    assert not lost, (
        "these finalize steps ran and their mark was then erased by the other "
        f"dispatch saving a stale copy of the anchor: {lost} "
        f"(persisted: {marks})"
    )


def _tracked_run_handler(side, events):
    async def run_handler(_redis_manager, _dep_task):
        events.append(side)
        await asyncio.sleep(0.05)
        events.append(side)
        return True

    return run_handler


def _sides_in_order(events):
    """The event sequence with consecutive same-side runs collapsed.

    Two entries means one side ran to completion and then the other did; more
    means they interleaved.
    """
    ordered = []
    for side in events:
        if not ordered or ordered[-1] != side:
            ordered.append(side)
    return ordered


@pytest.mark.asyncio
async def test_the_reconcile_heal_does_not_run_inside_a_dispatch(
    task_on_scratch_redis, repair_storage_new_slot  # noqa: F811
):
    """The heal mutates the same anchor a dispatch is marking.

    ``reconcile.run`` is a peer coroutine of the consumer under one
    ``asyncio.gather``, so the two really do run at the same time; the heal
    re-runs handlers, restatuses the chain and then deletes its jobs, all on
    an anchor a dispatch may be part way through.
    """
    from isardvdi_change_handler.streams import reconcile, task_results_consumer

    root = Task(**template_chain_kwargs())
    jobs = storage_jobs(task_on_scratch_redis)
    anchor_id = next(
        job_id for job_id, job in jobs.items() if (job.meta or {}).get("core_finalize")
    )
    for job_id in jobs:
        Job.fetch(job_id, connection=task_on_scratch_redis).set_status(JobStatus.FAILED)

    events = []

    def recorded_delete(_self, *_args, **_kwargs):
        # Recorded, not performed: really deleting the chain would leave the
        # dispatch with nothing to run whenever the heal won the race.
        events.append("heal")

    with (
        patch.object(task_results_consumer, "emit_task_feedback", new=AsyncMock()),
        patch.object(task_results_consumer, "handle_row_progress", new=AsyncMock()),
        patch.object(
            task_results_consumer,
            "_enqueue_metadata_storage_dependents",
            new=AsyncMock(return_value=True),
        ),
        patch.object(reconcile, "_release_storage_dependents", new=AsyncMock()),
        patch.object(
            task_results_consumer,
            "_run_handler",
            new=_tracked_run_handler("dispatch", events),
        ),
        patch.object(
            reconcile, "_run_handler", new=_tracked_run_handler("heal", events)
        ),
        patch.object(Job, "delete", recorded_delete),
    ):
        await asyncio.gather(
            task_results_consumer._process_entry(
                AsyncMock(), _result_event(jobs[root.id], "failed")
            ),
            reconcile._heal_core_orphan(AsyncMock(), Task(anchor_id)),
        )

    sides = set(events)
    assert sides == {
        "dispatch",
        "heal",
    }, f"both sides must have run for this to prove anything, got {sides}"
    ordered = _sides_in_order(events)
    assert len(ordered) <= 2, (
        "the reconcile heal and a dispatch mutated one anchor at the same "
        f"time: they changed hands {len(ordered) - 1} times ({ordered})"
    )
