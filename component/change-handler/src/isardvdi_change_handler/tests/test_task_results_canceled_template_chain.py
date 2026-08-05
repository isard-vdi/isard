# SPDX-License-Identifier: AGPL-3.0-or-later

"""A CANCELLED template-creation chain must still run its terminal
``update_status``.

The chain built by ``Storage.enqueue_template_creation_chain_from_desktop``
declares one step whose whole job is to settle the rows when the operation does
NOT succeed::

    move -> create -> qemu_img_info_backing_chain(template)
      -> core: storage_update
        -> storage: qemu_img_info_backing_chain(desktop)      <- THE KNOT
          -> core: storage_update
            -> core: update_status      # FAILED/CANCELED -> "Failed" for the
                                        # desktop, the template, and both
                                        # storage rows

``update_status`` sits *inside the knot child's subtree*. Whether the cancelled
chain reaches it is therefore a property of how the graph is built, and that is
exactly what this test pins.

This test is deliberately written to run unchanged on both sides of the
question, so it is evidence of *authorship* and not only of correctness:

* it drives the real chain definition (captured from the real ``Storage``
  builder, not hand-copied here),
* it builds the real rq graph through the real ``Task`` constructor against a
  real Redis,
* it cancels through the real ``Task.cancel``,
* and it feeds the consumer the cancel event that ``Task.cancel`` actually
  published, through the real ``_process_entry``.

The only things stubbed are the two edges of the system this suite does not
own: the SocketIO feedback emit, and the finalize handler bodies (which write
to RethinkDB) — replaced by recorders, so what is asserted is *which chain
members the consumer reached*.
"""

import pytest
from isardvdi_common.models.task import Task
from rq.job import JobStatus

from ._chain_harness import (
    DESKTOP_ID,
    DESKTOP_STORAGE_ID,
    TEMPLATE_ID,
    TEMPLATE_STORAGE_ID,
    canceled_event,
    first_core_step,
    recording_handlers,
    repair_storage_new_slot,  # noqa: F401  (fixture)
    template_chain_kwargs,
)


async def _dispatch_cancel(connection, root):
    """Cancel ``root`` and hand the consumer the event that cancel published."""
    from unittest.mock import AsyncMock, patch

    from isardvdi_change_handler.streams import task_results_consumer

    root.cancel()
    ran = []
    with (
        patch.object(task_results_consumer, "emit_task_feedback", new=AsyncMock()),
        patch.object(task_results_consumer, "HANDLERS", recording_handlers(ran)),
    ):
        await task_results_consumer._process_entry(
            AsyncMock(), canceled_event(connection)
        )
    return ran


@pytest.mark.asyncio
async def test_canceled_template_chain_runs_its_terminal_update_status(
    task_on_scratch_redis, repair_storage_new_slot  # noqa: F811
):
    """Cancel a template creation and the chain's declared terminal step must
    still run — it is the only thing that maps CANCELED onto ``Failed`` for the
    desktop, the template and both storage rows. Without it the four rows keep
    the transitional status the caller set before enqueuing, forever.
    """
    root = Task(**template_chain_kwargs())
    ran = await _dispatch_cancel(task_on_scratch_redis, root)

    dispatched = [name for name, _id, _kwargs in ran]
    assert "update_status" in dispatched, (
        "the cancelled chain never reached its terminal update_status; "
        f"it only dispatched {dispatched}"
    )

    statuses = next(
        kwargs["statuses"] for name, _id, kwargs in ran if name == "update_status"
    )
    # The step that ran is the chain's real terminal one, not some other
    # update_status: it settles all four rows the template creation touched.
    assert statuses[JobStatus.CANCELED]["Failed"] == {
        "domain": [DESKTOP_ID, TEMPLATE_ID],
        "storage": [DESKTOP_STORAGE_ID, TEMPLATE_STORAGE_ID],
    }


@pytest.mark.asyncio
async def test_the_terminal_step_runs_once_when_the_knot_child_does_exist(
    task_on_scratch_redis, repair_storage_new_slot  # noqa: F811
):
    """Cancel AFTER the anchor ran, so the knot child is a real member.

    Then the child carries its own finalize tree and is reached as the job it
    is. The chain must not ALSO be read out of the raw definition the parent
    step still carries, or one member would exist twice and every step below it
    would be dispatched twice.
    """
    from isardvdi_change_handler.streams import task_results_consumer

    root = Task(**template_chain_kwargs())
    step = first_core_step(root)
    assert await task_results_consumer._enqueue_metadata_storage_dependents(step)

    ran = await _dispatch_cancel(task_on_scratch_redis, root)

    dispatched = [name for name, _id, _kwargs in ran]
    assert dispatched.count("update_status") == 1, (
        f"the terminal step ran {dispatched.count('update_status')} times: {dispatched}"
    )
    assert len(set(step_id for _n, step_id, _k in ran)) == len(ran), (
        f"a finalize step was dispatched twice: {[s for _n, s, _k in ran]}"
    )
