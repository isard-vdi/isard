# SPDX-License-Identifier: AGPL-3.0-or-later

"""The task-result event wakes the migration reconciler for its migration."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from isardvdi_change_handler.streams import task_results_consumer as mod


# --------------------------------------------------------------------------- #
# _wake_migration — the wake itself
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_wake_calls_advance_without_abandon_detection():
    """``check_abandon=False`` is what makes an edge caller safe: a sibling's"""
    advance = MagicMock(return_value="done")
    with patch.object(mod, "advance", advance):
        assert await mod._wake_migration("mig-1") == "done"
    advance.assert_called_once_with("mig-1", check_abandon=False)


@pytest.mark.asyncio
async def test_wake_never_propagates_a_failure():
    """The wake is an optimisation over a backstop that still runs. Letting it"""
    with patch.object(mod, "advance", MagicMock(side_effect=RuntimeError("redis"))):
        assert await mod._wake_migration("mig-1") is None


@pytest.mark.asyncio
async def test_wake_runs_off_the_event_loop():
    """``advance`` is blocking (redis lease + database), so it must not run on"""
    with patch.object(mod, "advance", MagicMock(return_value=None)):
        with patch.object(
            mod.asyncio, "to_thread", new=AsyncMock(return_value=None)
        ) as to_thread:
            await mod._wake_migration("mig-1")
    to_thread.assert_awaited_once()


# --------------------------------------------------------------------------- #
# _process_entry — a result event carrying a migration_id wakes it
# --------------------------------------------------------------------------- #
@asynccontextmanager
async def _noop_lock(_ids):
    yield


def _quiet_dispatch():
    """Patch out everything a ``result`` entry does besides the wake."""
    return (
        patch.object(mod, "emit_task_feedback", new=AsyncMock()),
        patch.object(mod, "handle_row_progress", new=AsyncMock()),
        patch.object(
            mod,
            "Task",
            MagicMock(return_value=SimpleNamespace(id="t1", _redis=None, meta={})),
        ),
        patch.object(mod, "was_canceled", MagicMock(return_value=False)),
        patch.object(mod, "_set_job_status", new=AsyncMock()),
        patch.object(mod, "_record_service_time", MagicMock()),
        patch.object(mod, "_walk_core_dependents", MagicMock(return_value=iter(()))),
        patch.object(mod, "_anchor_lock", _noop_lock),
    )


@pytest.mark.asyncio
async def test_result_entry_with_migration_id_wakes_that_migration():
    wake = AsyncMock()
    patches = _quiet_dispatch()
    for p in patches:
        p.start()
    try:
        with patch.object(mod, "_wake_migration", wake):
            await mod._process_entry(
                AsyncMock(),
                {
                    "kind": "result",
                    "task_id": "t1",
                    "job_status": "finished",
                    "migration_id": "mig-7",
                },
            )
    finally:
        for p in patches:
            p.stop()
    wake.assert_awaited_once_with("mig-7")


@pytest.mark.asyncio
async def test_result_entry_without_migration_id_wakes_nothing():
    """Every storage task publishes a result event; only a migration's carries"""
    wake = AsyncMock()
    patches = _quiet_dispatch()
    for p in patches:
        p.start()
    try:
        with patch.object(mod, "_wake_migration", wake):
            await mod._process_entry(
                AsyncMock(),
                {"kind": "result", "task_id": "t1", "job_status": "finished"},
            )
    finally:
        for p in patches:
            p.stop()
    wake.assert_not_awaited()


@pytest.mark.asyncio
async def test_failed_task_wakes_too():
    """A failed move must reach the reconciler as promptly as a successful one:"""
    wake = AsyncMock()
    patches = _quiet_dispatch()
    for p in patches:
        p.start()
    try:
        with patch.object(mod, "_wake_migration", wake):
            await mod._process_entry(
                AsyncMock(),
                {
                    "kind": "result",
                    "task_id": "t1",
                    "job_status": "failed",
                    "migration_id": "mig-7",
                },
            )
    finally:
        for p in patches:
            p.stop()
    wake.assert_awaited_once_with("mig-7")


@pytest.mark.asyncio
async def test_progress_entry_does_not_wake():
    """A progress tick is not a phase boundary — there is nothing to advance,"""
    wake = AsyncMock()
    with (
        patch.object(mod, "emit_task_feedback", new=AsyncMock()),
        patch.object(mod, "handle_row_progress", new=AsyncMock()),
        patch.object(mod, "_wake_migration", wake),
    ):
        acked = await mod._process_entry(
            AsyncMock(),
            {"kind": "progress", "task_id": "t1", "migration_id": "mig-7"},
        )
    assert acked is True
    wake.assert_not_awaited()
