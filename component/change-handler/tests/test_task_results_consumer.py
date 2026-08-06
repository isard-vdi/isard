# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the ``stream:task-results`` consumer dispatch."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from isardvdi_common.models.task import CoreStep
from rq.job import JobStatus


def _core_step(node_id, task_name, kwargs=None):
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
        job_status=JobStatus.FINISHED, id=f"anchor-of-{node_id}", job=MagicMock()
    )
    return CoreStep(node, anchor, MagicMock())


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
        # No cancel record on this member. A bare MagicMock would answer
        # every hget truthily, i.e. "cancelled", which is the one thing a
        # default must never mean.
        _redis=MagicMock(**{"hget.return_value": None}),
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

    unknown_dep = _core_step("dep-unknown", "storage_domains_force_update")
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
        ok = await task_results_consumer._process_entry(
            redis_manager,
            {"kind": "result", "task_id": "root", "task_name": "find"},
        )
    # No handler for the step -> treated as a clean no-op: no raise, entry ACKs,
    # and the step is stamped so ``Task.pending`` stops counting it.
    assert ok is True
    assert unknown_dep._node["status"] == "finished"


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


# --- _release_storage_dependents: the REAL function, not a mock of it ---------
#
# The reconcile tests patch _release_storage_dependents with an AsyncMock, so its
# own gate (does this member have a storage-queue dependent?) and its core/storage
# boundary were never exercised. These drive the real function and spy only on the
# rq boundary (redis.from_url / Queue.enqueue_dependents).


def _member(dependents):
    return SimpleNamespace(id="m", job=MagicMock(name="job"), dependents=dependents)


def _dep_on(queue):
    return SimpleNamespace(queue=queue)


@pytest.mark.asyncio
async def test_release_storage_dependents_releases_a_member_with_a_storage_child():
    """A member with a storage-queue dependent must reach
    ``Queue.enqueue_dependents`` — that is the DEFERRED→QUEUED release the storage
    worker needs after a core handler."""
    from isardvdi_change_handler.streams import task_results_consumer as trc

    member = _member([_dep_on("storage.pool.default")])
    with (
        patch.object(trc.redis, "from_url", return_value=MagicMock()),
        patch.object(trc, "Queue") as queue_cls,
    ):
        await trc._release_storage_dependents(member)
    queue_cls.return_value.enqueue_dependents.assert_called_once_with(member.job)


@pytest.mark.asyncio
async def test_release_storage_dependents_skips_a_member_with_no_storage_child():
    """The gate: a member with no non-core dependent must NOT enqueue anything."""
    from isardvdi_change_handler.streams import task_results_consumer as trc

    member = _member([])
    with (
        patch.object(trc.redis, "from_url", return_value=MagicMock()),
        patch.object(trc, "Queue") as queue_cls,
    ):
        await trc._release_storage_dependents(member)
    queue_cls.return_value.enqueue_dependents.assert_not_called()


@pytest.mark.asyncio
async def test_release_storage_dependents_ignores_a_core_only_dependent():
    """The boundary: a ``core``-queue dependent is NOT a storage child, so a
    member that has only core dependents releases nothing."""
    from isardvdi_change_handler.streams import task_results_consumer as trc

    member = _member([_dep_on("core")])
    with (
        patch.object(trc.redis, "from_url", return_value=MagicMock()),
        patch.object(trc, "Queue") as queue_cls,
    ):
        await trc._release_storage_dependents(member)
    queue_cls.return_value.enqueue_dependents.assert_not_called()


class TestReapDeadConsumers:
    """Every start registers a fresh change-handler-<uuid4> and nothing removed
    the old one, so the group grew by one per restart. Measured on a live install
    (09/08/2026): 14 registered, 2 alive, 12 idle for 39 to 55 days. No entry
    is lost — XAUTOCLAIM reclaims what a dead consumer held — but XINFO GROUPS
    reports a count that has nothing to do with reality, and a "nobody is
    consuming" alert can never fire because the corpses keep it satisfied.
    """

    @staticmethod
    def _redis(consumers):
        redis = AsyncMock()
        redis.xinfo_consumers = AsyncMock(return_value=consumers)
        redis.xgroup_delconsumer = AsyncMock()
        return redis

    @pytest.mark.asyncio
    async def test_a_long_idle_empty_consumer_is_dropped(self):
        from isardvdi_change_handler.streams import task_results_consumer

        redis = self._redis(
            [{"name": "change-handler-old", "pending": 0, "idle": 55 * 86400 * 1000}]
        )
        reaped = await task_results_consumer._reap_dead_consumers(
            redis, "stream:task-results", "me"
        )
        assert reaped == 1
        redis.xgroup_delconsumer.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_our_own_consumer_is_never_dropped(self):
        """Idle is measured against the group, and our own entry is the one
        thing we know is alive — dropping it would unregister the live reader."""
        from isardvdi_change_handler.streams import task_results_consumer

        redis = self._redis([{"name": "me", "pending": 0, "idle": 99 * 86400 * 1000}])
        reaped = await task_results_consumer._reap_dead_consumers(
            redis, "stream:task-results", "me"
        )
        assert reaped == 0
        redis.xgroup_delconsumer.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_consumer_holding_entries_is_left_alone(self):
        """Deleting it would move its pending list instead of letting the
        reclaim pass redeliver what it was holding."""
        from isardvdi_change_handler.streams import task_results_consumer

        redis = self._redis(
            [{"name": "change-handler-old", "pending": 3, "idle": 55 * 86400 * 1000}]
        )
        reaped = await task_results_consumer._reap_dead_consumers(
            redis, "stream:task-results", "me"
        )
        assert reaped == 0
        redis.xgroup_delconsumer.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_recently_active_consumer_is_left_alone(self):
        from isardvdi_change_handler.streams import task_results_consumer

        redis = self._redis(
            [{"name": "change-handler-live", "pending": 0, "idle": 2828}]
        )
        reaped = await task_results_consumer._reap_dead_consumers(
            redis, "stream:task-results", "me"
        )
        assert reaped == 0
        redis.xgroup_delconsumer.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_a_redis_failure_does_not_stop_the_consumer_starting(self):
        from isardvdi_change_handler.streams import task_results_consumer

        redis = AsyncMock()
        redis.xinfo_consumers = AsyncMock(side_effect=RuntimeError("redis blip"))
        reaped = await task_results_consumer._reap_dead_consumers(
            redis, "stream:task-results", "me"
        )
        assert reaped == 0
