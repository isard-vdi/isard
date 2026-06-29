# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the storage/task-chain self-heal reconcile passes.

The reconcile recovers chains the consumer could not finish: a core handler
that raised leaves a storage-queue/core dependent stuck DEFERRED forever, the
storage row stuck ``maintenance`` and the domain stuck ``Downloading`` — and
``Task.pending`` then blocks every later op on that storage with a 428. These
tests pin the two idempotent passes and the safety gates (grace window,
never finalize a storage whose task is still alive).
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from rq.job import JobStatus


def _dep(status=JobStatus.FINISHED, ended_secs_ago=600):
    """A dependency Task double: a job_status + a job.ended_at."""
    ended = None
    if ended_secs_ago is not None:
        ended = datetime.now(timezone.utc) - timedelta(seconds=ended_secs_ago)
    return SimpleNamespace(job_status=status, job=SimpleNamespace(ended_at=ended))


def _task(
    task_id="t1",
    *,
    task_name="storage_update",
    queue="core",
    dependencies=None,
    dependents=None,
    user_id="u1",
):
    job = MagicMock(name=f"job-{task_id}")
    return SimpleNamespace(
        id=task_id,
        task=task_name,
        queue=queue,
        user_id=user_id,
        dependencies=dependencies if dependencies is not None else [_dep()],
        dependents=dependents or [],
        job=job,
        cancel=MagicMock(name=f"cancel-{task_id}"),
    )


# ---------------------------------------------------------------------------
# _deps_terminal_and_aged — the orphan gate
# ---------------------------------------------------------------------------


def test_orphan_gate_true_when_all_deps_terminal_and_aged():
    from isardvdi_change_handler.streams import reconcile

    now = datetime.now(timezone.utc)
    task = _task(dependencies=[_dep(JobStatus.FINISHED, 600)])
    assert reconcile._deps_terminal_and_aged(task, now, grace_s=120) is True


def test_orphan_gate_false_when_a_dep_not_terminal():
    from isardvdi_change_handler.streams import reconcile

    now = datetime.now(timezone.utc)
    task = _task(dependencies=[_dep(JobStatus.STARTED, 600)])
    assert reconcile._deps_terminal_and_aged(task, now, grace_s=120) is False


def test_orphan_gate_false_within_grace_window():
    from isardvdi_change_handler.streams import reconcile

    now = datetime.now(timezone.utc)
    task = _task(dependencies=[_dep(JobStatus.FINISHED, 5)])  # finished 5s ago
    assert reconcile._deps_terminal_and_aged(task, now, grace_s=120) is False


def test_orphan_gate_false_when_no_dependencies():
    from isardvdi_change_handler.streams import reconcile

    now = datetime.now(timezone.utc)
    task = _task(dependencies=[])
    assert reconcile._deps_terminal_and_aged(task, now, grace_s=120) is False


def test_orphan_gate_false_when_ended_at_missing():
    from isardvdi_change_handler.streams import reconcile

    now = datetime.now(timezone.utc)
    task = _task(dependencies=[_dep(JobStatus.FINISHED, None)])
    assert reconcile._deps_terminal_and_aged(task, now, grace_s=120) is False


def test_orphan_gate_handles_naive_ended_at():
    from isardvdi_change_handler.streams import reconcile

    now = datetime.now(timezone.utc)
    naive_old = (datetime.now(timezone.utc) - timedelta(seconds=600)).replace(
        tzinfo=None
    )
    dep = SimpleNamespace(
        job_status=JobStatus.FINISHED,
        job=SimpleNamespace(ended_at=naive_old),
    )
    task = _task(dependencies=[dep])
    assert reconcile._deps_terminal_and_aged(task, now, grace_s=120) is True


# ---------------------------------------------------------------------------
# Pass 1 — orphaned DEFERRED jobs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_pass1_core_orphan_replays_dispatch_and_deletes():
    """A core-queue orphan re-runs the handler, marks FINISHED, releases its
    storage dependents and deletes the dead core job."""
    from isardvdi_change_handler.streams import reconcile

    orphan = _task("core1", queue="core", task_name="storage_update")
    with (
        patch.object(reconcile.Task, "get_by_status", return_value=[orphan]),
        patch.object(reconcile, "_walk_core_dependents", return_value=[]),
        patch.object(
            reconcile, "_run_handler", new=AsyncMock(return_value=True)
        ) as run_h,
        patch.object(reconcile, "_set_job_status", new=AsyncMock()) as set_st,
        patch.object(reconcile, "_release_storage_dependents", new=AsyncMock()) as rel,
    ):
        healed = await reconcile._reconcile_orphan_deferred(AsyncMock())

    assert healed == 1
    run_h.assert_awaited()
    set_st.assert_awaited_with(orphan, JobStatus.FINISHED)
    rel.assert_awaited_with(orphan)
    orphan.job.delete.assert_called_once()


@pytest.mark.asyncio
async def test_pass1_failed_handler_marks_failed_and_does_not_release():
    from isardvdi_change_handler.streams import reconcile

    orphan = _task("core1", queue="core")
    with (
        patch.object(reconcile.Task, "get_by_status", return_value=[orphan]),
        patch.object(reconcile, "_walk_core_dependents", return_value=[]),
        patch.object(reconcile, "_run_handler", new=AsyncMock(return_value=False)),
        patch.object(reconcile, "_set_job_status", new=AsyncMock()) as set_st,
        patch.object(reconcile, "_release_storage_dependents", new=AsyncMock()) as rel,
    ):
        await reconcile._reconcile_orphan_deferred(AsyncMock())

    set_st.assert_awaited_with(orphan, JobStatus.FAILED)
    rel.assert_not_awaited()


@pytest.mark.asyncio
async def test_pass1_skips_orphan_within_grace():
    from isardvdi_change_handler.streams import reconcile

    fresh = _task("core1", queue="core", dependencies=[_dep(JobStatus.FINISHED, 5)])
    with (
        patch.object(reconcile.Task, "get_by_status", return_value=[fresh]),
        patch.object(reconcile, "_run_handler", new=AsyncMock()) as run_h,
    ):
        healed = await reconcile._reconcile_orphan_deferred(AsyncMock())

    assert healed == 0
    run_h.assert_not_awaited()


@pytest.mark.asyncio
async def test_pass1_storage_orphan_with_finished_parent_is_released():
    from isardvdi_change_handler.streams import reconcile

    parent = _dep(JobStatus.FINISHED, 600)
    orphan = _task("stg1", queue="storage.default.low", dependencies=[parent])
    with (
        patch.object(reconcile.Task, "get_by_status", return_value=[orphan]),
        patch.object(reconcile, "_release_via_parents", new=AsyncMock()) as rel,
    ):
        healed = await reconcile._reconcile_orphan_deferred(AsyncMock())

    assert healed == 1
    rel.assert_awaited_with(orphan)
    orphan.cancel.assert_not_called()


@pytest.mark.asyncio
async def test_pass1_storage_orphan_with_failed_parent_is_cancelled():
    from isardvdi_change_handler.streams import reconcile

    parent = _dep(JobStatus.FAILED, 600)
    orphan = _task("stg1", queue="storage.default.low", dependencies=[parent])
    with (
        patch.object(reconcile.Task, "get_by_status", return_value=[orphan]),
        patch.object(reconcile, "_release_via_parents", new=AsyncMock()) as rel,
    ):
        healed = await reconcile._reconcile_orphan_deferred(AsyncMock())

    assert healed == 1
    orphan.job.cancel.assert_called_once()
    rel.assert_not_awaited()


# ---------------------------------------------------------------------------
# Pass 2 — storages stuck in maintenance whose task is dead
# ---------------------------------------------------------------------------


def _storage(
    sid="s1",
    *,
    status="maintenance",
    task="oldtask",
    virtual_size=171798691840,
    user_id="u1",
):
    s = MagicMock(name=f"storage-{sid}")
    s.id = sid
    s.status = status
    s.task = task
    s.user_id = user_id
    qi = {"virtual-size": virtual_size} if virtual_size is not None else None
    # ``qemu-img-info`` is not a valid attr name; the model exposes it via getattr
    setattr(s, "qemu-img-info", qi)
    return s


@pytest.mark.asyncio
async def test_pass2_valid_disk_promoted_to_ready():
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(virtual_size=171798691840)
    with (
        patch.object(reconcile.Storage, "get_index", return_value=[storage]),
        patch.object(reconcile, "_task_alive", return_value=False),
        patch.object(reconcile, "_apply_storage_update") as apply_u,
        patch.object(reconcile, "send_status_socket", new=AsyncMock()) as sock,
    ):
        healed = await reconcile._reconcile_stuck_storage(AsyncMock())

    assert healed == 1
    apply_u.assert_called_once_with({"id": "s1", "status": "ready"})
    sock.assert_awaited_once()


@pytest.mark.asyncio
async def test_pass2_skips_storage_with_live_task():
    from isardvdi_change_handler.streams import reconcile

    storage = _storage()
    with (
        patch.object(reconcile.Storage, "get_index", return_value=[storage]),
        patch.object(reconcile, "_task_alive", return_value=True),
        patch.object(reconcile, "_apply_storage_update") as apply_u,
        patch.object(reconcile, "send_status_socket", new=AsyncMock()),
    ):
        healed = await reconcile._reconcile_stuck_storage(AsyncMock())

    assert healed == 0
    apply_u.assert_not_called()


@pytest.mark.asyncio
async def test_pass2_invalid_disk_rechecks_chain_not_finalized():
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(virtual_size=0)
    storage.check_backing_chain = MagicMock()
    with (
        patch.object(reconcile.Storage, "get_index", return_value=[storage]),
        patch.object(reconcile, "_task_alive", return_value=False),
        patch.object(reconcile, "_apply_storage_update") as apply_u,
        patch.object(reconcile, "send_status_socket", new=AsyncMock()),
    ):
        healed = await reconcile._reconcile_stuck_storage(AsyncMock())

    assert healed == 0
    apply_u.assert_not_called()
    storage.check_backing_chain.assert_called_once()


def test_task_alive_false_when_task_missing():
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(task=None)
    assert reconcile._task_alive(storage) is False


def test_task_alive_false_when_task_not_pending():
    from isardvdi_change_handler.streams import reconcile

    storage = _storage(task="t9")
    with (
        patch.object(reconcile.Task, "exists", return_value=True),
        patch.object(reconcile, "Task", wraps=reconcile.Task) as TaskCls,
    ):
        TaskCls.exists.return_value = True
        inst = MagicMock()
        inst.pending = False
        TaskCls.return_value = inst
        assert reconcile._task_alive(storage) is False


# ---------------------------------------------------------------------------
# run() — eager pass + periodic loop
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_run_invokes_both_passes_then_sleeps():
    from isardvdi_change_handler.streams import reconcile

    calls = {"orphan": 0, "stuck": 0}

    async def _fake_orphan(rm, *a, **k):
        calls["orphan"] += 1
        return 0

    async def _fake_stuck(rm, *a, **k):
        calls["stuck"] += 1
        return 0

    class _Stop(Exception):
        pass

    async def _sleep_then_stop(_s):
        raise _Stop()

    with (
        patch.object(reconcile, "_reconcile_orphan_deferred", new=_fake_orphan),
        patch.object(reconcile, "_reconcile_stuck_storage", new=_fake_stuck),
        patch.object(reconcile.asyncio, "sleep", new=_sleep_then_stop),
    ):
        with pytest.raises(_Stop):
            await reconcile.run(AsyncMock(), interval_s=1)

    assert calls["orphan"] == 1
    assert calls["stuck"] == 1
