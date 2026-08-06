# SPDX-License-Identifier: AGPL-3.0-or-later

"""The knot child's declared id, and why an unfetchable one must NOT be pending.

A knot child's id is deterministic and declared on the anchor at chain-build
time, so between "the anchor finished" and "the consumer created the child"
there is an id in ``dependent_ids`` that cannot be fetched. ``_chain_closure``
skips ids it cannot fetch, so the declared child is invisible for that moment,
exactly like an undeclared one — which is what made a transient blindness
window a live question.

The standing proposal was to close it by making a DECLARED id that cannot be
fetched count as pending, on the reasoning that post-build-time-declaration an
unfetchable id means "this will exist" rather than "this was deleted".

**Measured, that reasoning does not hold, and the change would be a
regression.** Two facts decide it:

* The window is already covered. The thing that creates the knot child is a
  finalize step, and during the whole window that step is UNSTAMPED — so
  ``chain_pending`` already answers True, by counting the step rather than by
  guessing about the id.
* On a cancelled or failed chain the knot child is never created *by design*,
  so its declared id is unfetchable FOREVER. Under the proposed rule every
  cancelled template chain would read pending for ever. And it would be
  unrecoverable: the finalize steps of a cancelled chain do all run, so
  ``finalize_has_unstamped`` is False and the orphan hatch never opens. That is
  "428 forever" reintroduced on the cancel path.

So the answer to the open question is "no change", and these tests exist to
keep it that way — the second one fails if someone implements the proposal.
"""

import pytest
from isardvdi_common.models.task import Task, _chain_closure
from rq.job import Job, JobStatus

from ._chain_harness import repair_storage_new_slot  # noqa: F401  (fixture)
from ._chain_harness import first_core_step, template_chain_kwargs
from .test_task_results_canceled_template_chain import _dispatch_cancel


def _settle_real_jobs(connection, root, status=JobStatus.FINISHED):
    for job in _chain_closure(root.job, connection).values():
        job.set_status(status)
        job.save()


def test_the_window_is_covered_by_the_step_that_will_create_the_child(
    task_on_scratch_redis, repair_storage_new_slot  # noqa: F811
):
    """Anchor FINISHED, knot child not yet created: the chain is still busy,
    and it is the unstamped finalize step that says so — not the id."""
    root = Task(**template_chain_kwargs())
    step = first_core_step(root)
    _settle_real_jobs(task_on_scratch_redis, root)

    declared = list(step.knot_child_ids)
    assert declared, "the chain declared no knot child"
    assert not any(
        Job.exists(child_id, connection=task_on_scratch_redis) for child_id in declared
    ), "premise: the child has not been created yet"
    assert step._node.get("status") is None, "premise: its finalize step has not run"

    assert Task(root.id).chain_pending is True, (
        "the chain read as settled while the step that creates the knot child "
        "had not run"
    )


@pytest.mark.asyncio
async def test_a_cancelled_chain_does_not_stay_pending_on_a_child_never_created(
    task_on_scratch_redis, repair_storage_new_slot  # noqa: F811
):
    """The guard against closing the window the other way.

    A cancelled template chain never creates its knot child, so the declared id
    stays unfetchable for ever. If an unfetchable declared id counted as
    pending, this chain would be pending for ever — and the orphan hatch could
    not save it, because a cancelled chain's finalize steps all ran.
    """
    root = Task(**template_chain_kwargs())
    step = first_core_step(root)
    declared = list(step.knot_child_ids)

    await _dispatch_cancel(task_on_scratch_redis, root)

    assert not any(
        Job.exists(child_id, connection=task_on_scratch_redis) for child_id in declared
    ), "premise: a cancelled chain never creates its knot child"
    assert declared, "premise: the id was still declared on the anchor"

    assert Task(root.id).chain_pending is False, (
        "a cancelled chain reads as pending on a knot child that will never "
        "exist: nothing can ever clear this row"
    )
