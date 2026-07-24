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
from rq.job import JobStatus


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

    dep = _stub_task("dep", task_name="update_status", kwargs={"id": "s1"})
    root = _stub_task("root", task_name="delete", queue="storage.pool.reclaim",
                      dependents=[dep])
    handler = AsyncMock()
    emit_p, task_p, handlers_p = _patch_dispatch(root, {"update_status": (handler, True)})

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
async def test_canceled_chain_deletes_only_canceled_core_jobs():
    """Cancelled core members are dropped, but a FINISHED core member is left
    alone — it may still be the replay state of an earlier pending entry."""
    from isardvdi_change_handler.streams import task_results_consumer

    canceled_dep = _stub_task("dep-canceled", task_name="update_status",
                              job_status=JobStatus.CANCELED)
    finished_dep = _stub_task("dep-finished", task_name="storage_update",
                              job_status=JobStatus.FINISHED)
    root = _stub_task("root", task_name="delete", queue="storage.pool.reclaim",
                      dependents=[canceled_dep, finished_dep])
    emit_p, task_p, handlers_p = _patch_dispatch(
        root, {"update_status": (AsyncMock(), True), "storage_update": (AsyncMock(), True)}
    )

    with emit_p, task_p, handlers_p:
        await task_results_consumer._process_entry(
            AsyncMock(),
            {"kind": "canceled", "task_id": "root", "job_status": "canceled"},
        )

    canceled_dep.job.delete.assert_called_once()
    finished_dep.job.delete.assert_not_called()


@pytest.mark.asyncio
async def test_canceled_chain_does_not_release_storage_dependents():
    """Releasing a cancelled member's deferred storage children would run work
    for an operation the user cancelled."""
    from isardvdi_change_handler.streams import task_results_consumer

    dep = _stub_task("dep", task_name="update_status", job_status=JobStatus.CANCELED)
    root = _stub_task("root", task_name="delete", queue="storage.pool.reclaim",
                      dependents=[dep])
    emit_p, task_p, handlers_p = _patch_dispatch(root, {"update_status": (AsyncMock(), True)})

    with emit_p, task_p, handlers_p, patch(
        "isardvdi_change_handler.streams.task_results_consumer._release_storage_dependents",
        new=AsyncMock(),
    ) as release:
        await task_results_consumer._process_entry(
            AsyncMock(),
            {"kind": "canceled", "task_id": "root", "job_status": "canceled"},
        )

    release.assert_not_awaited()


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
    root = _stub_task("root", queue="storage.pool.maintenance",
                      dependents=[canceled_storage])

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
    root = _stub_task("root", queue="storage.pool.maintenance",
                      dependents=[storage_stage])

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
