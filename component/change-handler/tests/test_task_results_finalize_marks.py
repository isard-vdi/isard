# SPDX-License-Identifier: AGPL-3.0-or-later

"""The finalize marks must survive the dispatch that made them.

A ``CoreStep`` is retired by stamping ``node["status"]`` — that mark is what
tells a later sibling its dependency settled, what stops ``Task.pending``
counting the step as active work, and what lets the reconcile tell a finished
chain from a stuck one. The node lives inside the ``meta`` of the rq job that
carries the finalize tree (its *anchor*), and a mark is only durable once that
job's meta is saved.

``_process_entry`` saves exactly one job's meta: the one the event was keyed
on. But a dispatch spans several anchors — in the template chain the finalize
tree hangs off the third storage job, not off the root the event names — so
every mark it makes is written to an object nobody saves and is lost the
moment the pass ends.
"""

import pytest
from isardvdi_common.models.task import Task
from rq.job import Job

from ._chain_harness import repair_storage_new_slot  # noqa: F401  (fixture)
from ._chain_harness import (
    canceled_event,
    finalize_nodes,
    recording_handlers,
    storage_jobs,
    template_chain_kwargs,
)


@pytest.mark.asyncio
async def test_finalize_marks_persist_on_the_anchor_that_carries_them(
    task_on_scratch_redis, repair_storage_new_slot  # noqa: F811
):
    """Every finalize step the dispatch stamped must read back stamped.

    Re-read from Redis, not from the in-memory objects the dispatch used: the
    defect is precisely that the mark exists in memory and never reaches the
    hash.
    """
    from unittest.mock import AsyncMock, patch

    from isardvdi_change_handler.streams import task_results_consumer

    root = Task(**template_chain_kwargs())
    root.cancel()

    ran = []
    with (
        patch.object(task_results_consumer, "emit_task_feedback", new=AsyncMock()),
        patch.object(task_results_consumer, "HANDLERS", recording_handlers(ran)),
    ):
        await task_results_consumer._process_entry(
            AsyncMock(), canceled_event(task_on_scratch_redis)
        )

    dispatched = [step_id for _name, step_id, _kwargs in ran]
    assert dispatched, "nothing was dispatched — the harness, not the defect, is broken"

    persisted = {}
    for job in storage_jobs(task_on_scratch_redis).values():
        fresh = Job.fetch(job.id, connection=task_on_scratch_redis)
        for node in finalize_nodes(fresh):
            persisted[node["id"]] = node["status"]

    unstamped = [step_id for step_id in dispatched if persisted.get(step_id) is None]
    assert not unstamped, (
        "these finalize steps ran but their mark was never persisted: "
        f"{unstamped} (persisted marks: {persisted})"
    )
    # A cancelled chain produced nothing, so every step it ran is a failure.
    assert set(persisted[step_id] for step_id in dispatched) == {"failed"}
