# SPDX-License-Identifier: AGPL-3.0-or-later

"""The finalize-orphan hatch, asked the way the reconcile actually asks it.

``_task_alive`` looks a row's chain up by ``storage.task``, which is the id of
the chain's ROOT. But the job whose meta carries ``core_finalize`` is not the
root: in the real template chain it is the third storage job, the one whose
result the finalize hangs off. So a hatch that reads ``core_finalize`` off the
task it was handed can never open for the one chain shape that has a knot.

That matters only once an unstamped finalize step counts as pending — and then
it matters absolutely, because a lost result event would pin the chain pending
for ever and the reconcile could never heal that row again. Which is why the
hatch has to be closure-wide BEFORE the predicate gets stricter, not after.

These tests build the real chain with the product's own builder, so the shape
they assert on is the shape the product ships rather than a fixture's idea of
it.
"""

from datetime import datetime, timedelta, timezone

import pytest
from isardvdi_common.models.task import Task, _chain_closure
from rq.job import Job, JobStatus

from ._chain_harness import repair_storage_new_slot  # noqa: F401  (fixture)
from ._chain_harness import first_core_step, template_chain_kwargs

# Comfortably past the consumer's redelivery envelope (5 reclaims of 60s).
AGED_S = 5000
MIN_AGE_S = 900


def _settle_every_real_job(connection, root, *, aged_s=AGED_S, status=None):
    """Every rq job in the chain terminal and settled long ago — the state a
    chain is left in when its work finished and the result event was lost."""
    ended = datetime.now(timezone.utc) - timedelta(seconds=aged_s)
    for job in _chain_closure(root.job, connection).values():
        job.set_status(status or JobStatus.FINISHED)
        job.ended_at = ended
        job.save()


def test_the_anchor_is_not_the_root(
    task_on_scratch_redis, repair_storage_new_slot
):  # noqa: F811
    """The premise the rest of this file rests on. If the builder ever puts the
    finalize on the root, these tests stop testing what they claim to."""
    root = Task(**template_chain_kwargs())

    closure = _chain_closure(root.job, task_on_scratch_redis)
    anchors = [
        job_id
        for job_id, job in closure.items()
        if (getattr(job, "meta", None) or {}).get("core_finalize")
    ]

    assert anchors, "no job in the chain carries core_finalize"
    assert root.id not in anchors, (
        "the finalize now hangs off the chain root; the knot shape this file "
        "exists for has changed and these tests need rewriting"
    )


def test_the_hatch_opens_for_a_chain_whose_finalize_hangs_off_a_deeper_job(
    task_on_scratch_redis, repair_storage_new_slot  # noqa: F811
):
    """The whole point. Asked from the root — which is what ``storage.task``
    holds and therefore what ``_task_alive`` passes — the hatch must still see
    the unstamped finalize sitting on a deeper member."""
    from isardvdi_change_handler.streams import reconcile

    root = Task(**template_chain_kwargs())
    _settle_every_real_job(task_on_scratch_redis, root)

    assert (
        reconcile._metadata_finalize_orphaned(
            Task(root.id), datetime.now(timezone.utc), MIN_AGE_S
        )
        is True
    ), (
        "the hatch stayed shut for a settled chain with an unstamped finalize: "
        "a lost result event would pin this row pending for ever"
    )


def test_the_hatch_stays_shut_while_a_deeper_member_is_still_running(
    task_on_scratch_redis, repair_storage_new_slot  # noqa: F811
):
    """The hatch says 'not live work'. A chain with a worker still on it is
    live work, and healing it would act on a disk that is being written."""
    from isardvdi_change_handler.streams import reconcile

    root = Task(**template_chain_kwargs())
    _settle_every_real_job(task_on_scratch_redis, root)

    # The anchor itself is the deepest real job in this chain: put a worker
    # back on it.
    closure = _chain_closure(root.job, task_on_scratch_redis)
    anchor = next(
        job for job in closure.values() if (job.meta or {}).get("core_finalize")
    )
    anchor.set_status(JobStatus.STARTED)
    anchor.save()

    assert (
        reconcile._metadata_finalize_orphaned(
            Task(root.id), datetime.now(timezone.utc), MIN_AGE_S
        )
        is False
    ), "the hatch opened on a chain a worker is still running"


@pytest.mark.asyncio
async def test_the_hatch_stays_shut_when_the_knot_child_is_still_running(
    task_on_scratch_redis, repair_storage_new_slot  # noqa: F811
):
    """The knot child is the member the old one-level walk could not see at
    all. It is a real rq job doing real disk work, and the hatch must count
    it."""
    from isardvdi_change_handler.streams import reconcile, task_results_consumer

    root = Task(**template_chain_kwargs())
    step = first_core_step(root)
    created = await task_results_consumer._enqueue_metadata_storage_dependents(step)
    assert created, "the harness failed to create the knot child"

    _settle_every_real_job(task_on_scratch_redis, root)

    child_id = next(iter(step.knot_child_ids))
    child = Job.fetch(child_id, connection=task_on_scratch_redis)
    child.set_status(JobStatus.STARTED)
    child.save()

    assert (
        reconcile._metadata_finalize_orphaned(
            Task(root.id), datetime.now(timezone.utc), MIN_AGE_S
        )
        is False
    ), "the hatch opened while the knot child was still converting a disk"


def test_the_hatch_stays_shut_when_every_finalize_step_already_ran(
    task_on_scratch_redis, repair_storage_new_slot  # noqa: F811
):
    """Nothing was lost, so there is nothing to heal."""
    from isardvdi_change_handler.streams import reconcile

    root = Task(**template_chain_kwargs())
    _settle_every_real_job(task_on_scratch_redis, root)

    closure = _chain_closure(root.job, task_on_scratch_redis)
    for job in closure.values():
        finalize = (job.meta or {}).get("core_finalize")
        if not finalize:
            continue
        _stamp_all(finalize)
        job.save()

    assert (
        reconcile._metadata_finalize_orphaned(
            Task(root.id), datetime.now(timezone.utc), MIN_AGE_S
        )
        is False
    ), "the hatch opened on a chain whose finalize had already applied"


def test_the_hatch_stays_shut_inside_the_redelivery_envelope(
    task_on_scratch_redis, repair_storage_new_slot  # noqa: F811
):
    """A just-settled chain is one the consumer is probably about to finalize.
    Opening here would race the redelivery the hatch exists to outlast."""
    from isardvdi_change_handler.streams import reconcile

    root = Task(**template_chain_kwargs())
    _settle_every_real_job(task_on_scratch_redis, root, aged_s=100)

    assert (
        reconcile._metadata_finalize_orphaned(
            Task(root.id), datetime.now(timezone.utc), MIN_AGE_S
        )
        is False
    ), "the hatch opened inside the redelivery envelope"


def test_the_hatch_stays_shut_for_a_legacy_chain_with_no_finalize_metadata(
    task_on_scratch_redis, repair_storage_new_slot  # noqa: F811
):
    """A chain built before metadata finalize carries no ``core_finalize`` at
    all. There is no finalize to have been lost, so this hatch has no opinion
    and must not claim one."""
    from isardvdi_change_handler.streams import reconcile

    root = Task(**template_chain_kwargs())
    _settle_every_real_job(task_on_scratch_redis, root)

    for job in _chain_closure(root.job, task_on_scratch_redis).values():
        if (job.meta or {}).pop("core_finalize", None) is not None:
            job.save()

    assert (
        reconcile._metadata_finalize_orphaned(
            Task(root.id), datetime.now(timezone.utc), MIN_AGE_S
        )
        is False
    ), "the hatch opened on a chain that has no metadata finalize at all"


def _stamp_all(nodes):
    for node in nodes or []:
        node["status"] = "finished"
        _stamp_all(node.get("core_finalize"))
