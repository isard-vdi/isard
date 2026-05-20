# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the ``stream:task-results`` consumer dispatch."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest


def _stub_task(
    task_id,
    *,
    task_name="storage_update",
    queue="core",
    dependents=None,
    depending_status="finished",
    kwargs=None,
):
    """Lightweight Task double that ``_walk_core_dependents`` can iterate."""
    return SimpleNamespace(
        id=task_id,
        task=task_name,
        queue=queue,
        depending_status=depending_status,
        kwargs=kwargs or {},
        dependents=dependents or [],
    )


@pytest.mark.asyncio
async def test_progress_kind_only_emits_feedback():
    """``kind=progress`` triggers ``emit_task_feedback`` and nothing else."""
    from isardvdi_change_handler.streams import task_results_consumer

    redis_manager = AsyncMock()
    with (
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.emit_task_feedback",
            new=AsyncMock(),
        ) as mock_emit,
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.Task"
        ) as mock_task_cls,
    ):
        await task_results_consumer._process_entry(
            redis_manager,
            {"kind": "progress", "task_id": "t1", "task_name": "move"},
        )
        mock_emit.assert_awaited_once_with(redis_manager, "t1")
        mock_task_cls.assert_not_called()


@pytest.mark.asyncio
async def test_result_kind_emits_feedback_then_dispatches_dependents():
    """``kind=result`` emits feedback AND drives core dependents through the registry."""
    from isardvdi_change_handler.streams import task_results_consumer

    dep_a = _stub_task(
        "dep-a", task_name="storage_update_pool", kwargs={"storage_id": "s1"}
    )
    dep_b = _stub_task(
        "dep-b",
        task_name="storage_update_parent",
        kwargs={"storage_id": "s1"},
    )
    root = _stub_task("root", dependents=[dep_a])
    dep_a.dependents = [dep_b]

    redis_manager = AsyncMock()
    pool_handler = AsyncMock()
    parent_handler = AsyncMock()

    fake_registry = {
        "storage_update_pool": (pool_handler, True),
        "storage_update_parent": (parent_handler, False),
    }

    with (
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.emit_task_feedback",
            new=AsyncMock(),
        ) as mock_emit,
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.Task",
            return_value=root,
        ),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.HANDLERS",
            fake_registry,
        ),
    ):
        await task_results_consumer._process_entry(
            redis_manager,
            {"kind": "result", "task_id": "root", "task_name": "find"},
        )

    mock_emit.assert_awaited_once_with(redis_manager, "root")
    pool_handler.assert_awaited_once_with(redis_manager, dep_a, storage_id="s1")
    parent_handler.assert_called_once_with(dep_b, storage_id="s1")


@pytest.mark.asyncio
async def test_storage_queue_dependents_are_skipped():
    """Dependents on storage queues will publish their own stream events and must not be walked."""
    from isardvdi_change_handler.streams import task_results_consumer

    storage_dep = _stub_task(
        "dep-storage",
        task_name="qemu_img_info_backing_chain",
        queue="storage.poolA.default",
    )
    core_dep = _stub_task(
        "dep-core",
        task_name="storage_update",
        queue="core",
        kwargs={"id": "s1", "status": "ready"},
    )
    root = _stub_task("root", dependents=[storage_dep, core_dep])

    redis_manager = AsyncMock()
    update_handler = AsyncMock()
    storage_chain_handler = AsyncMock()
    fake_registry = {
        "storage_update": (update_handler, True),
        "qemu_img_info_backing_chain": (storage_chain_handler, True),
    }

    with (
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
            fake_registry,
        ),
    ):
        await task_results_consumer._process_entry(
            redis_manager,
            {"kind": "result", "task_id": "root", "task_name": "find"},
        )

    update_handler.assert_awaited_once_with(
        redis_manager, core_dep, id="s1", status="ready"
    )
    storage_chain_handler.assert_not_called()
    storage_chain_handler.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_task_name_is_skipped_without_raising():
    """A core-queue dependent with no registered handler is logged-and-skipped."""
    from isardvdi_change_handler.streams import task_results_consumer

    unknown_dep = _stub_task(
        "dep-unknown",
        task_name="storage_domains_force_update",
        queue="core",
    )
    root = _stub_task("root", dependents=[unknown_dep])
    redis_manager = AsyncMock()

    with (
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
            {},
        ),
    ):
        await task_results_consumer._process_entry(
            redis_manager,
            {"kind": "result", "task_id": "root", "task_name": "find"},
        )
    # No assert needed — getting here without raising is the contract.


@pytest.mark.asyncio
async def test_missing_task_id_is_skipped():
    """Malformed stream entry without a task_id is silently dropped (no raise)."""
    from isardvdi_change_handler.streams import task_results_consumer

    redis_manager = AsyncMock()
    with patch(
        "isardvdi_change_handler.streams.task_results_consumer.emit_task_feedback",
        new=AsyncMock(),
    ) as mock_emit:
        await task_results_consumer._process_entry(redis_manager, {"kind": "result"})
    mock_emit.assert_not_awaited()


@pytest.mark.asyncio
async def test_unknown_kind_is_skipped():
    """Unknown ``kind`` value drops the entry without raising."""
    from isardvdi_change_handler.streams import task_results_consumer

    redis_manager = AsyncMock()
    with patch(
        "isardvdi_change_handler.streams.task_results_consumer.emit_task_feedback",
        new=AsyncMock(),
    ) as mock_emit:
        await task_results_consumer._process_entry(
            redis_manager, {"kind": "weird", "task_id": "t1"}
        )
    mock_emit.assert_not_awaited()


def test_walk_core_dependents_is_depth_first():
    """The walker yields each core-queue dependent in pre-order, skipping storage branches."""
    from isardvdi_change_handler.streams.task_results_consumer import (
        _walk_core_dependents,
    )

    leaf_a = _stub_task("a", queue="core")
    leaf_b = _stub_task("b", queue="core")
    leaf_storage = _stub_task("s", queue="storage.poolA.default")
    middle = _stub_task("m", queue="core", dependents=[leaf_a, leaf_storage])
    root = _stub_task("root", dependents=[middle, leaf_b])

    yielded = [t.id for t in _walk_core_dependents(root)]
    assert yielded == ["m", "a", "b"]


@pytest.mark.asyncio
async def test_handler_exception_is_logged_but_loop_continues():
    """A failing handler must not abort the dispatch of sibling dependents."""
    from isardvdi_change_handler.streams import task_results_consumer

    bad = _stub_task("bad", task_name="storage_update", queue="core")
    good = _stub_task(
        "good", task_name="storage_add", queue="core", kwargs={"id": "s2"}
    )
    root = _stub_task("root", dependents=[bad, good])

    redis_manager = AsyncMock()
    raising = AsyncMock(side_effect=RuntimeError("boom"))
    succeeding_sync = AsyncMock()  # sync registry entries are wrapped via to_thread

    fake_registry = {
        "storage_update": (raising, True),
        "storage_add": (succeeding_sync, False),
    }

    with (
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
            fake_registry,
        ),
    ):
        await task_results_consumer._process_entry(
            redis_manager,
            {"kind": "result", "task_id": "root", "task_name": "find"},
        )

    raising.assert_awaited_once()
    succeeding_sync.assert_called_once_with(good, id="s2")
