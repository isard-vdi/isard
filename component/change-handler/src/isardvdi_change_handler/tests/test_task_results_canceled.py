# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the ``kind=canceled`` branch of the task-results consumer.

A cancelled job never publishes a result of its own, so without a dedicated
event the chain's finalize handlers would only run on the next reconcile pass
— leaving the storage row in ``maintenance`` in the meantime.

The event is deliberately its own kind rather than a ``result``: the result
path maps any non-``failed`` status to FINISHED, so a cancelled delete chain
arriving as a result would take the success branch and drop a storage row
whose file is still on disk.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from isardvdi_common.models.task import CoreStep
from rq.job import JobStatus


def _core_step(node_id, task_name="storage_update", kwargs=None):
    """A real metadata finalize step (the only kind the consumer dispatches)."""
    node = {
        "id": node_id,
        "task": task_name,
        "queue": "core",
        "kwargs": kwargs or {},
        "args": [],
        "core_finalize": [],
        "storage_dependents": [],
        "status": None,
    }
    # The parent stands in for the step's ANCHOR: the real rq job whose meta
    # carries this node, and where the consumer makes the step's mark durable.
    # It therefore needs an id and a job, like the Task it doubles for.
    anchor = SimpleNamespace(
        job_status=JobStatus.CANCELED, id=f"anchor-of-{node_id}", job=MagicMock()
    )
    return CoreStep(node, anchor, MagicMock())


def _stub_task(
    task_id,
    *,
    task_name="storage_update",
    queue="core",
    dependents=None,
    depending_status="canceled",
    kwargs=None,
    job_status=JobStatus.CANCELED,
):
    job = MagicMock(name=f"job-{task_id}")
    job.get_status.return_value = job_status
    return SimpleNamespace(
        id=task_id,
        task=task_name,
        queue=queue,
        depending_status=depending_status,
        kwargs=kwargs or {},
        dependents=dependents or [],
        job=job,
        # No cancel record on this member. A bare MagicMock would answer
        # every hget truthily, i.e. "cancelled", which is the one thing a
        # default must never mean.
        _redis=MagicMock(**{"hget.return_value": None}),
        job_status=job_status,
    )


def _patch_dispatch(root, handlers=None):
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
            "isardvdi_change_handler.streams.task_results_consumer.HANDLERS",
            handlers if handlers is not None else {},
        ),
    )


@pytest.mark.asyncio
async def test_canceled_kind_runs_core_finalizers():
    """The cancelled chain's core handlers run, so the row leaves
    ``maintenance`` without waiting for a reconcile tick."""
    from isardvdi_change_handler.streams import task_results_consumer

    dep = _core_step("dep", task_name="update_status", kwargs={"id": "s1"})
    root = _stub_task(
        "root", task_name="delete", queue="storage.pool.reclaim", dependents=[dep]
    )
    handler = AsyncMock()
    emit_p, task_p, handlers_p = _patch_dispatch(
        root, {"update_status": (handler, True)}
    )

    with emit_p, task_p, handlers_p:
        ok = await task_results_consumer._process_entry(
            AsyncMock(),
            {"kind": "canceled", "task_id": "root", "job_status": "canceled"},
        )

    assert ok is True
    handler.assert_awaited_once()


@pytest.mark.asyncio
async def test_canceled_kind_does_not_overwrite_the_root_status():
    """The root is already CANCELED (or legitimately FINISHED for a mid-chain
    cancel) — the cancelled branch must never rewrite it to FINISHED."""
    from isardvdi_change_handler.streams import task_results_consumer

    root = _stub_task("root", task_name="delete", queue="storage.pool.reclaim")
    emit_p, task_p, handlers_p = _patch_dispatch(root)

    with emit_p, task_p, handlers_p:
        await task_results_consumer._process_entry(
            AsyncMock(),
            {"kind": "canceled", "task_id": "root", "job_status": "canceled"},
        )

    root.job.set_status.assert_not_called()


@pytest.mark.asyncio
async def test_canceled_member_status_is_never_rewritten():
    """``_set_job_status`` must leave a CANCELED job alone: a late worker
    event, a redelivery or a reconcile heal must not flip it to FINISHED,
    or handlers deeper in the chain would read ``depending_status=finished``
    and run their success bodies on a dead chain."""
    from isardvdi_change_handler.streams import task_results_consumer

    dep = _stub_task("dep", job_status=JobStatus.CANCELED)

    await task_results_consumer._set_job_status(dep, JobStatus.FINISHED)

    dep.job.set_status.assert_not_called()


@pytest.mark.asyncio
async def test_non_canceled_member_status_is_still_written():
    """The guard must not break the normal path."""
    from isardvdi_change_handler.streams import task_results_consumer

    dep = _stub_task("dep", job_status=JobStatus.DEFERRED)

    await task_results_consumer._set_job_status(dep, JobStatus.FINISHED)

    dep.job.set_status.assert_called_once_with(JobStatus.FINISHED)


@pytest.mark.asyncio
@pytest.mark.parametrize("gone", ["InvalidJobOperation", "NoSuchJobError"])
async def test_a_job_whose_data_is_gone_is_not_resurrected(gone):
    """A job that no longer exists must not be written to.

    ``set_status`` is a bare ``HSET``, so a write against a deleted job
    RECREATES its hash, and the ``ended_at`` stamp that follows completes it
    into something indistinguishable from a settled chain member. The heal
    reaches here right after deleting a healed chain's jobs, so a redelivery
    lands on exactly the ids it just removed.
    """
    import rq.exceptions
    from isardvdi_change_handler.streams import task_results_consumer

    dep = _stub_task("dep", job_status=JobStatus.DEFERRED)
    dep.job.get_status.side_effect = getattr(rq.exceptions, gone)("gone")

    await task_results_consumer._set_job_status(dep, JobStatus.FINISHED)

    dep.job.set_status.assert_not_called()


@pytest.mark.asyncio
async def test_a_status_we_merely_could_not_read_is_still_written():
    """The guard is about a job that is GONE, not about a Redis blip.

    An ordinary read failure keeps the previous fail-open behaviour: refusing
    the write there would leave the step unmarked and strand every handler
    behind it on ``depending_status != finished``.
    """
    from isardvdi_change_handler.streams import task_results_consumer

    dep = _stub_task("dep", job_status=JobStatus.DEFERRED)
    dep.job.get_status.side_effect = ConnectionError("redis blip")

    await task_results_consumer._set_job_status(dep, JobStatus.FINISHED)

    dep.job.set_status.assert_called_once_with(JobStatus.FINISHED)


@pytest.mark.asyncio
async def test_canceled_kind_emits_feedback():
    """The frontend must learn the chain settled, not keep spinning."""
    from isardvdi_change_handler.streams import task_results_consumer

    root = _stub_task("root", task_name="delete", queue="storage.pool.reclaim")
    emit_p, task_p, handlers_p = _patch_dispatch(root)

    with emit_p as mock_emit, task_p, handlers_p:
        await task_results_consumer._process_entry(
            AsyncMock(),
            {"kind": "canceled", "task_id": "root", "job_status": "canceled"},
        )

    mock_emit.assert_awaited_once()


def test_walk_reaches_core_finalizers_behind_a_canceled_storage_member():
    """A cancelled storage stage publishes no event of its own, so its core
    finalizers are only reachable by recursing THROUGH it."""
    from isardvdi_change_handler.streams import task_results_consumer

    nested_core = _stub_task("nested-core", queue="core")
    canceled_storage = _stub_task(
        "storage-stage",
        queue="storage.pool.maintenance",
        job_status=JobStatus.CANCELED,
        dependents=[nested_core],
    )
    root = _stub_task(
        "root", queue="storage.pool.maintenance", dependents=[canceled_storage]
    )

    found = list(
        task_results_consumer._walk_core_dependents(root, include_canceled_storage=True)
    )

    assert [t.id for t in found] == ["nested-core"]


def test_walk_default_still_stops_at_storage_boundary():
    """The normal result path must keep its behaviour: a storage dependent
    drives its own dispatch when its worker publishes."""
    from isardvdi_change_handler.streams import task_results_consumer

    nested_core = _stub_task("nested-core", queue="core")
    storage_stage = _stub_task(
        "storage-stage",
        queue="storage.pool.maintenance",
        job_status=JobStatus.DEFERRED,
        dependents=[nested_core],
    )
    root = _stub_task(
        "root", queue="storage.pool.maintenance", dependents=[storage_stage]
    )

    assert list(task_results_consumer._walk_core_dependents(root)) == []


def test_walk_survives_a_cyclic_chain():
    """Malformed meta must not blow the stack."""
    from isardvdi_change_handler.streams import task_results_consumer

    a = _stub_task("a", queue="core")
    b = _stub_task("b", queue="core", dependents=[a])
    a.dependents = [b]
    root = _stub_task("root", queue="storage.pool.maintenance", dependents=[a])

    found = [t.id for t in task_results_consumer._walk_core_dependents(root)]

    assert sorted(found) == ["a", "b"]


def test_walk_passes_through_a_finished_storage_member_on_a_dead_chain():
    """Traversal is not rewriting.

    A chain cancelled half way has FINISHED members between the root and the
    cancelled one. Refusing to walk past them leaves everything below the
    cancel unreachable, so a cancelled template creation is announced and
    nothing settles the rows. Passing THROUGH a finished member does not touch
    its history — it only reaches steps that never ran.
    """
    from isardvdi_change_handler.streams import task_results_consumer

    behind = _core_step("behind")
    canceled_stage = _stub_task(
        "canceled-stage",
        queue="storage.pool.template",
        job_status=JobStatus.CANCELED,
        dependents=[behind],
    )
    finished_stage = _stub_task(
        "finished-stage",
        queue="storage.pool.template",
        job_status=JobStatus.FINISHED,
        dependents=[canceled_stage],
    )
    root = _stub_task(
        "root",
        queue="storage.pool.template",
        job_status=JobStatus.FINISHED,
        dependents=[finished_stage],
    )

    found = list(
        task_results_consumer._walk_core_dependents(
            root, include_canceled_storage=True, dead_chain=True
        )
    )

    assert [t.id for t in found] == ["behind"]


def test_walk_does_not_pass_through_a_finished_storage_member_on_a_live_chain():
    """On a chain still succeeding, each storage member publishes its own
    result and drives its own dispatch. Walking past it here would run the
    finalize steps behind it a second time — and before the work they
    finalise has happened."""
    from isardvdi_change_handler.streams import task_results_consumer

    behind = _core_step("behind")
    finished_stage = _stub_task(
        "finished-stage",
        queue="storage.pool.template",
        job_status=JobStatus.FINISHED,
        dependents=[behind],
    )
    root = _stub_task(
        "root",
        queue="storage.pool.template",
        job_status=JobStatus.FINISHED,
        dependents=[finished_stage],
    )

    found = list(task_results_consumer._walk_core_dependents(root))

    assert found == []


@pytest.mark.asyncio
async def test_a_step_that_already_ran_is_not_re_run_on_a_dead_chain():
    """Passing through a completed step must not re-execute it.

    Walking a cancelled chain reaches the steps behind the cancel by passing
    through the ones that already succeeded. Re-dispatching those re-applies
    their success bodies — and the walk yields them AFTER the failure branch
    has run, so a template just marked Failed is promoted back to ready by a
    step re-running work it had already done. Traversal is not re-execution.
    """
    from isardvdi_change_handler.streams import task_results_consumer

    done = _core_step("already-done", task_name="storage_update")
    done.mark(True)
    behind = _core_step("behind", task_name="update_status")
    canceled_child = _stub_task(
        "canceled-child",
        queue="storage.pool.template",
        job_status=JobStatus.CANCELED,
        dependents=[behind],
    )
    anchor = _stub_task(
        "anchor",
        queue="storage.pool.template",
        job_status=JobStatus.FINISHED,
        dependents=[canceled_child, done],
    )
    root = _stub_task(
        "root",
        queue="storage.pool.template",
        job_status=JobStatus.FINISHED,
        dependents=[anchor],
    )

    ran = []
    handlers = {
        "storage_update": (lambda t, **k: ran.append("storage_update"), False),
        "update_status": (lambda t, **k: ran.append("update_status"), False),
    }
    emit_p, task_p, handlers_p = _patch_dispatch(root, handlers)
    with emit_p, task_p, handlers_p:
        await task_results_consumer._process_entry(
            AsyncMock(),
            {"kind": "canceled", "task_id": "root", "job_status": "canceled"},
        )

    assert ran == ["update_status"], f"a completed step was re-run: {ran}"
    assert done._node["status"] == "finished"
