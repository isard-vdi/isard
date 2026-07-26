# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the ``stream:task-results`` consumer dispatch."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

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
    """Lightweight Task double that ``_walk_core_dependents`` can iterate.

    Includes a ``job.set_status`` mock so the consumer's
    in-process FINISHED/FAILED transition (the replacement for the
    RQ-worker marking core_worker used to provide) can be asserted.
    """
    job = MagicMock(name=f"job-{task_id}")
    return SimpleNamespace(
        id=task_id,
        task=task_name,
        queue=queue,
        depending_status=depending_status,
        kwargs=kwargs or {},
        dependents=dependents or [],
        job=job,
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
async def test_failed_core_handler_does_not_release_dependents():
    """When a core handler raises, the chain has failed — its deferred
    storage child MUST stay deferred so the chain doesn't advance past a
    bad state.
    """
    from isardvdi_change_handler.streams import task_results_consumer

    storage_grandchild = _stub_task(
        "storage-child",
        task_name="qemu_img_info_backing_chain",
        queue="storage.poolA.default",
    )
    core_dep = _stub_task(
        "core-dep",
        task_name="storage_update",
        queue="core",
        dependents=[storage_grandchild],
    )
    root = _stub_task("root", dependents=[core_dep])

    redis_manager = AsyncMock()
    raising = AsyncMock(side_effect=RuntimeError("boom"))
    fake_registry = {"storage_update": (raising, True)}
    fake_queue = MagicMock()
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
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.Queue",
            return_value=fake_queue,
        ),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.redis.from_url",
            return_value=MagicMock(),
        ),
    ):
        await task_results_consumer._process_entry(
            redis_manager,
            {"kind": "result", "task_id": "root", "task_name": "find"},
        )

    fake_queue.enqueue_dependents.assert_not_called()


@pytest.mark.asyncio
async def test_core_dep_with_only_core_children_does_not_call_queue():
    """When a core dep has only core-queue children, the consumer must not
    spin up an RQ Queue or call enqueue_dependents. Avoids touching Redis
    for the common case of a tail of core handlers.
    """
    from isardvdi_change_handler.streams import task_results_consumer

    grand_core = _stub_task("grand", task_name="update_status", queue="core")
    core_dep = _stub_task(
        "core-dep",
        task_name="storage_update",
        queue="core",
        kwargs={"id": "s1"},
        dependents=[grand_core],
    )
    root = _stub_task("root", dependents=[core_dep])

    redis_manager = AsyncMock()
    fake_registry = {
        "storage_update": (AsyncMock(), True),
        "update_status": (AsyncMock(), True),
    }
    fake_queue = MagicMock()
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
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.Queue",
            return_value=fake_queue,
        ),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.redis.from_url",
            return_value=MagicMock(),
        ),
    ):
        await task_results_consumer._process_entry(
            redis_manager,
            {"kind": "result", "task_id": "root", "task_name": "find"},
        )

    fake_queue.enqueue_dependents.assert_not_called()


# ---------------------------------------------------------------------------
# At-least-once: success-only ACK + delete, PEL retry, dead-letter
# ---------------------------------------------------------------------------


def _patch_dispatch(root):
    """Common patches for a _process_entry call rooted at ``root``."""
    return (
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.emit_task_feedback",
            new=AsyncMock(),
        ),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.Task",
            return_value=root,
        ),
    )


@pytest.mark.asyncio
async def test_process_entry_returns_false_when_task_hydration_fails():
    from isardvdi_change_handler.streams import task_results_consumer

    with (
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.emit_task_feedback",
            new=AsyncMock(),
        ),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.Task",
            side_effect=RuntimeError("redis down"),
        ),
    ):
        ok = await task_results_consumer._process_entry(
            AsyncMock(), {"kind": "result", "task_id": "x", "task_name": "find"}
        )

    assert ok is False


@pytest.mark.asyncio
async def test_read_and_dispatch_acks_only_on_success():
    from isardvdi_change_handler.streams import task_results_consumer

    redis = AsyncMock()
    redis.xreadgroup.return_value = [("s", [("1-0", {"kind": "result"})])]
    with patch.object(
        task_results_consumer, "_process_entry", new=AsyncMock(return_value=True)
    ):
        await task_results_consumer._read_and_dispatch(redis, AsyncMock(), "c1")
    redis.xack.assert_awaited_once_with(
        task_results_consumer.STREAM_KEY,
        task_results_consumer.CONSUMER_GROUP,
        "1-0",
    )


@pytest.mark.asyncio
async def test_read_and_dispatch_does_not_ack_on_failure():
    from isardvdi_change_handler.streams import task_results_consumer

    redis = AsyncMock()
    redis.xreadgroup.return_value = [("s", [("1-0", {"kind": "result"})])]
    with patch.object(
        task_results_consumer, "_process_entry", new=AsyncMock(return_value=False)
    ):
        await task_results_consumer._read_and_dispatch(redis, AsyncMock(), "c1")
    redis.xack.assert_not_awaited()


@pytest.mark.asyncio
async def test_read_and_dispatch_does_not_ack_when_process_raises():
    from isardvdi_change_handler.streams import task_results_consumer

    redis = AsyncMock()
    redis.xreadgroup.return_value = [("s", [("1-0", {"kind": "result"})])]
    with patch.object(
        task_results_consumer,
        "_process_entry",
        new=AsyncMock(side_effect=RuntimeError("boom")),
    ):
        await task_results_consumer._read_and_dispatch(redis, AsyncMock(), "c1")
    redis.xack.assert_not_awaited()


@pytest.mark.asyncio
async def test_reclaim_redispatches_idle_entry_and_acks_on_success():
    from isardvdi_change_handler.streams import task_results_consumer

    redis = AsyncMock()
    redis.xautoclaim.return_value = ["0-0", [("1-0", {"kind": "result"})]]
    redis.xpending_range.return_value = [{"times_delivered": 2}]
    with patch.object(
        task_results_consumer, "_process_entry", new=AsyncMock(return_value=True)
    ) as proc:
        await task_results_consumer._reclaim_pending(redis, AsyncMock(), "c1")

    proc.assert_awaited_once()
    redis.xack.assert_awaited_once()
    redis.xadd.assert_not_awaited()


@pytest.mark.asyncio
async def test_reclaim_dead_letters_after_max_deliveries():
    from isardvdi_change_handler.streams import task_results_consumer

    redis = AsyncMock()
    fields = {"kind": "result", "task_id": "poison"}
    redis.xautoclaim.return_value = ["0-0", [("1-0", fields)]]
    redis.xpending_range.return_value = [
        {"times_delivered": task_results_consumer.MAX_DELIVERIES + 1}
    ]
    with patch.object(task_results_consumer, "_process_entry", new=AsyncMock()) as proc:
        await task_results_consumer._reclaim_pending(redis, AsyncMock(), "c1")

    proc.assert_not_awaited()  # poison entry is NOT re-run
    redis.xadd.assert_awaited_once_with(
        task_results_consumer.DEAD_STREAM,
        fields,
        maxlen=task_results_consumer.DEAD_STREAM_MAXLEN,
        approximate=True,
    )
    redis.xack.assert_awaited_once()


@pytest.mark.asyncio
async def test_reclaim_does_not_ack_failed_redispatch():
    """A reclaimed entry whose redispatch fails again stays in the PEL (not
    ACKed) for the next sweep — until it crosses MAX_DELIVERIES."""
    from isardvdi_change_handler.streams import task_results_consumer

    redis = AsyncMock()
    redis.xautoclaim.return_value = ["0-0", [("1-0", {"kind": "result"})]]
    redis.xpending_range.return_value = [{"times_delivered": 2}]
    with patch.object(
        task_results_consumer, "_process_entry", new=AsyncMock(return_value=False)
    ):
        await task_results_consumer._reclaim_pending(redis, AsyncMock(), "c1")

    redis.xack.assert_not_awaited()
    redis.xadd.assert_not_awaited()


# ---------------------------------------------------------------------------
# Terminal-status propagation: the root Job must reflect the event's
# ``job_status``, not be force-marked FINISHED. Otherwise a root-terminal
# chain (convert / delete / virt_win_reg) whose ``update_status`` keys off the
# root reads ``finished`` and takes the SUCCESS branch on a failed/cancelled
# op — marking a half-written disk ready or dropping a storage row whose
# delete never completed.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_failed_job_status_marks_root_failed():
    """``job_status=failed`` on the result event marks the root Job FAILED."""
    from isardvdi_change_handler.streams import task_results_consumer
    from rq.job import JobStatus

    root = _stub_task("root", task_name="convert", dependents=[])
    with (
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.emit_task_feedback",
            new=AsyncMock(),
        ),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.Task",
            return_value=root,
        ),
        patch("isardvdi_change_handler.streams.task_results_consumer.HANDLERS", {}),
    ):
        await task_results_consumer._process_entry(
            AsyncMock(),
            {
                "kind": "result",
                "task_id": "root",
                "task_name": "convert",
                "job_status": "failed",
            },
        )

    root.job.set_status.assert_called_once_with(JobStatus.FAILED)


@pytest.mark.asyncio
async def test_finished_job_status_marks_root_finished():
    """``job_status=finished`` on the event marks the root Job FINISHED."""
    from isardvdi_change_handler.streams import task_results_consumer
    from rq.job import JobStatus

    root = _stub_task("root", task_name="convert", dependents=[])
    with (
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.emit_task_feedback",
            new=AsyncMock(),
        ),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.Task",
            return_value=root,
        ),
        patch("isardvdi_change_handler.streams.task_results_consumer.HANDLERS", {}),
    ):
        await task_results_consumer._process_entry(
            AsyncMock(),
            {
                "kind": "result",
                "task_id": "root",
                "task_name": "convert",
                "job_status": "finished",
            },
        )

    root.job.set_status.assert_called_once_with(JobStatus.FINISHED)


@pytest.mark.asyncio
async def test_missing_job_status_defaults_to_finished():
    """An event without ``job_status`` keeps the legacy FINISHED default so
    the publish-before-RQ-marks race stays closed for finished chains."""
    from isardvdi_change_handler.streams import task_results_consumer
    from rq.job import JobStatus

    root = _stub_task("root", task_name="find", dependents=[])
    with (
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.emit_task_feedback",
            new=AsyncMock(),
        ),
        patch(
            "isardvdi_change_handler.streams.task_results_consumer.Task",
            return_value=root,
        ),
        patch("isardvdi_change_handler.streams.task_results_consumer.HANDLERS", {}),
    ):
        await task_results_consumer._process_entry(
            AsyncMock(),
            {"kind": "result", "task_id": "root", "task_name": "find"},
        )

    root.job.set_status.assert_called_once_with(JobStatus.FINISHED)
