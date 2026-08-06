# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pass 1 of the reconcile as a PRODUCER: what it may place, and where.

``_heal_storage_orphan`` releases a DEFERRED storage job onto its lane. That is
an enqueue like any other, made by a background pass with nobody watching, so
the lane it targets has to be asked about first — a release onto a pool whose
workers are gone converts an orphan this pass re-enumerates every tick (and so
would eventually heal) into a QUEUED job nothing will ever hydrate, which
``Task.pending`` counts as live work for ever.

The CANCEL branch is the deliberate exception and is pinned here too: cancelling
a doomed orphan places nothing on the lane, so it must keep working on a dead
pool — that is precisely when a stuck row most needs settling.

Nothing here imports the gate itself: these are the behaviours, stated so they
read the same on either side of the fix. The lane verdict is steered at
``queue_coverage.lane_shed_decision``, the one decision both postures share.
"""

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rq.job import JobStatus

_DECISION = "isardvdi_common.lib.queue_coverage.lane_shed_decision"


def _dep(status=JobStatus.FINISHED, ended_secs_ago=600):
    """A dependency Task double: a job_status + a job.ended_at."""
    ended = None
    if ended_secs_ago is not None:
        ended = datetime.now(timezone.utc) - timedelta(seconds=ended_secs_ago)
    return SimpleNamespace(job_status=status, job=SimpleNamespace(ended_at=ended))


def _task(
    task_id="stg1",
    *,
    task_name="storage_update",
    queue="storage.default.bulk",
    dependencies=None,
    user_id="u1",
):
    """A DEFERRED storage-queue orphan, shaped like the ones in test_reconcile.py.

    ``_redis`` matters here beyond the cancel record: it is the connection any
    lane question is asked over, and a double without it dies with AttributeError
    inside the pass's per-task ``except`` — which reads as "the orphan was
    abandoned" rather than "the stub is incomplete".
    """
    job = MagicMock(name=f"job-{task_id}")
    redis = MagicMock(name=f"redis-{task_id}")
    redis.hget.return_value = None
    return SimpleNamespace(
        id=task_id,
        task=task_name,
        queue=queue,
        user_id=user_id,
        dependencies=dependencies if dependencies is not None else [_dep()],
        dependents=[],
        job=job,
        _redis=redis,
        cancel=MagicMock(name=f"cancel-{task_id}"),
    )


@contextmanager
def _lane(decision, reason=None, pool="default", tier="bulk"):
    """Force the fleet verdict for every lane looked at inside the block.

    Steered at the shared decision rather than at any caller, so the test says
    "this pool has no live worker" and lets the code under test decide what that
    means. A build that never asks simply never calls this mock.
    """
    ctx = {"pool": pool, "category": None, "tier": tier}
    if reason is not None:
        ctx["reason"] = reason
    with patch(_DECISION, return_value=(decision, ctx)) as decide:
        yield decide


@pytest.mark.asyncio
async def test_storage_orphan_not_released_onto_lane_with_no_consumer():
    """A release onto a dead pool strands the job QUEUED for ever and pins its
    storage at 428 ``storage_pending_task`` until an operator deletes it by hand.
    """
    from isardvdi_change_handler.streams import reconcile

    orphan = _task(dependencies=[_dep(JobStatus.FINISHED, 600)])
    with (
        _lane("reject", "no_consumer"),
        patch.object(reconcile, "_release_via_parents", new=AsyncMock()) as rel,
    ):
        healed = await reconcile._heal_storage_orphan(orphan)

    rel.assert_not_awaited()
    # Left DEFERRED is left where the next tick finds it: this pass IS the retry
    # loop, so declining costs nothing but the tick.
    assert healed == 0
    orphan.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_pass_does_not_count_an_orphan_it_declined_to_release():
    """``reconcile: healed N`` is the only operator-visible signal that the
    self-heal works; counting an orphan still stuck DEFERRED makes a pass that
    healed nothing look like a pass that healed everything.
    """
    from isardvdi_change_handler.streams import reconcile

    orphan = _task(dependencies=[_dep(JobStatus.FINISHED, 600)])
    with (
        _lane("reject", "no_consumer"),
        patch.object(reconcile.Task, "get_by_status", return_value=[orphan]),
        patch.object(reconcile, "_release_via_parents", new=AsyncMock()) as rel,
    ):
        healed = await reconcile._reconcile_orphan_deferred(AsyncMock())

    assert healed == 0
    rel.assert_not_awaited()


@pytest.mark.asyncio
async def test_storage_orphan_is_still_released_on_a_healthy_lane():
    """A gate that declined on a live pool too would silently retire the whole
    self-heal: every chain the consumer dropped would stay DEFERRED for ever.
    """
    from isardvdi_change_handler.streams import reconcile

    orphan = _task(dependencies=[_dep(JobStatus.FINISHED, 600)])
    with (
        _lane("ok"),
        patch.object(reconcile.Task, "get_by_status", return_value=[orphan]),
        patch.object(reconcile, "_release_via_parents", new=AsyncMock()) as rel,
    ):
        healed = await reconcile._reconcile_orphan_deferred(AsyncMock())

    assert healed == 1
    rel.assert_awaited_with(orphan)
    orphan.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_failed_parent_orphan_is_cancelled_even_with_no_consumer():
    """Cancelling is not a producer action — it places no work on the lane — so
    gating it would leave a doomed orphan DEFERRED on a dead pool with its
    storage stuck ``maintenance`` behind a task that can never settle, which is
    exactly the wedge a dead pool most needs the reconcile to clear.
    """
    from isardvdi_change_handler.streams import reconcile

    orphan = _task(dependencies=[_dep(JobStatus.FAILED, 600)])
    with (
        _lane("reject", "no_consumer") as decide,
        patch.object(reconcile, "_release_via_parents", new=AsyncMock()) as rel,
    ):
        healed = await reconcile._heal_storage_orphan(orphan)

    # Through ``Task.cancel``, which settles the whole chain: rq's raw
    # ``job.cancel(enqueue_dependents=True)`` promotes dependents onto a dead queue.
    orphan.cancel.assert_called_once_with()
    orphan.job.cancel.assert_not_called()
    rel.assert_not_awaited()
    assert healed == 1
    # And the lane was never even consulted: the doomed branch returns first.
    decide.assert_not_called()
