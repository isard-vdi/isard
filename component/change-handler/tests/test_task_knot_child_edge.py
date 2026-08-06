# SPDX-License-Identifier: AGPL-3.0-or-later

"""A knot child must be part of the chain that produced it.

A storage task nested under a ``core`` finalize step (the knot) has no rq job
when the chain is built: the step is metadata, so there is no DEFERRED job for
rq to promote, and the consumer creates the child when the step runs.

Created that way the child is born detached — nothing points at it and it
points at nothing — so from the chain's root the entire second half of the work
is invisible. Every consumer of the graph inherits that blindness: the closure
walk, ``Task.cancel``, the rendered chain, and the reconcile's judgement about
whether a row's work is still running.

Both ids are deterministic at build time, so the edge can be declared before
the anchor ever runs. These tests pin that it is.
"""

import pytest
from isardvdi_common.models.task import Task, _chain_closure
from rq.job import Job, JobStatus

from ._chain_harness import repair_storage_new_slot  # noqa: F401  (fixture)
from ._chain_harness import first_core_step, template_chain_kwargs


async def _build_chain_and_enqueue_the_knot_child(connection):
    """Build the real chain and run the real code that creates the knot child,
    as the consumer does when the anchor's finalize step runs."""
    from isardvdi_change_handler.streams import task_results_consumer

    root = Task(**template_chain_kwargs())
    step = first_core_step(root)
    assert step.storage_dependents, "this finalize step carries no knot child"
    ok = await task_results_consumer._enqueue_metadata_storage_dependents(step)
    assert ok, "the harness failed to create the knot child"
    return root, step


@pytest.mark.asyncio
async def test_a_created_knot_child_is_reachable_from_the_chain_root(
    task_on_scratch_redis, repair_storage_new_slot  # noqa: F811
):
    """The closure walk is what ``Task.cancel``, the 428 gate and the reconcile
    all read. A member missing from it is a member they cannot act on."""
    root, _step = await _build_chain_and_enqueue_the_knot_child(task_on_scratch_redis)

    closure = _chain_closure(root.job, task_on_scratch_redis)

    knot_children = [
        job_id
        for job_id, job in closure.items()
        if (job.func_name or "").endswith("qemu_img_info_backing_chain")
        and job.origin.startswith("storage.src-pool")
    ]
    assert knot_children, (
        "the knot child is not in the chain closure of its own root; "
        f"closure holds {sorted((j.func_name, j.origin) for j in closure.values())}"
    )


@pytest.mark.asyncio
async def test_cancel_reaches_a_knot_child_that_is_already_running(
    task_on_scratch_redis, repair_storage_new_slot  # noqa: F811
):
    """Cancel while the second half of the chain is in flight — the disk
    operation the user asked to stop is precisely the one the knot child runs,
    so a cancel that cannot reach it stops nothing."""
    root, step = await _build_chain_and_enqueue_the_knot_child(task_on_scratch_redis)
    child_id = next(iter(step.knot_child_ids))
    Job.fetch(child_id, connection=task_on_scratch_redis).set_status(JobStatus.STARTED)

    root.cancel()

    child = Job.fetch(child_id, connection=task_on_scratch_redis)
    assert (
        child.get_status(refresh=True) == JobStatus.CANCELED
    ), f"the running knot child {child_id} survived a cancel of its own chain"


@pytest.mark.asyncio
async def test_the_chain_has_one_root_once_the_knot_child_exists(
    task_on_scratch_redis, repair_storage_new_slot  # noqa: F811
):
    """``Task.cancel`` announces the cancel once per closure root. A knot child
    with no dependency of its own reads as a second root, which would publish a
    second cancel event and dispatch the whole finalize chain twice."""
    from isardvdi_common.models.task import _closure_roots

    root, _step = await _build_chain_and_enqueue_the_knot_child(task_on_scratch_redis)

    roots = _closure_roots(_chain_closure(root.job, task_on_scratch_redis))

    assert [job.id for job in roots] == [root.id], (
        "the closure has more than one root: " f"{[(j.id, j.func_name) for j in roots]}"
    )
