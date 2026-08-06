# SPDX-License-Identifier: AGPL-3.0-or-later

"""Guard / decision paths of ``streams/task_results_consumer.py``.

* ``_ensure_consumer_group`` -- swallows BUSYGROUP, re-raises any other ResponseError.
* ``_delivery_count`` -- returns the PEL delivery count, or 0 on error.
* ``_reclaim_pending`` -- drops trimmed (empty-fields) entries, dead-letters a
  poison entry past MAX_DELIVERIES, and re-processes+ACKs a normal one.
* ``_walk_core_dependents`` -- yields only core-queue dependents (recursively),
  skips storage members, recurses through a CANCELLED storage member, and is
  cycle-safe.

Only redis / the sibling helpers are stubbed; the decisions are the code's.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from isardvdi_change_handler.streams import task_results_consumer as mod
from redis.exceptions import ResponseError


class TestEnsureConsumerGroup:
    @pytest.mark.asyncio
    async def test_busygroup_is_swallowed(self):
        redis = SimpleNamespace(
            xgroup_create=AsyncMock(
                side_effect=ResponseError(
                    "BUSYGROUP Consumer Group name already exists"
                )
            )
        )
        # Must not raise.
        assert await mod._ensure_consumer_group(redis) is None

    @pytest.mark.asyncio
    async def test_other_response_error_reraises(self):
        redis = SimpleNamespace(
            xgroup_create=AsyncMock(side_effect=ResponseError("ERR unexpected"))
        )
        with pytest.raises(ResponseError):
            await mod._ensure_consumer_group(redis)


class TestDeliveryCount:
    @pytest.mark.asyncio
    async def test_returns_times_delivered(self):
        redis = SimpleNamespace(
            xpending_range=AsyncMock(return_value=[{"times_delivered": 4}])
        )
        assert await mod._delivery_count(redis, "1-0") == 4

    @pytest.mark.asyncio
    async def test_error_returns_none_not_zero(self):
        # Unreadable is not "never delivered": a zero here compares below
        # MAX_DELIVERIES for ever, so the entry could never be dead-lettered.
        redis = SimpleNamespace(xpending_range=AsyncMock(side_effect=RuntimeError()))
        assert await mod._delivery_count(redis, "1-0") is None

    @pytest.mark.asyncio
    async def test_empty_returns_zero(self):
        redis = SimpleNamespace(xpending_range=AsyncMock(return_value=[]))
        assert await mod._delivery_count(redis, "1-0") == 0


class TestReclaimPending:
    def _redis(self, entries):
        return SimpleNamespace(
            xautoclaim=AsyncMock(return_value=[b"0-0", entries]),
            xack=AsyncMock(),
            xadd=AsyncMock(),
        )

    @pytest.mark.asyncio
    async def test_trimmed_entry_is_dropped(self):
        redis = self._redis([("1-0", {})])  # empty fields => trimmed
        with patch.object(mod, "_process_entry", AsyncMock()) as proc:
            await mod._reclaim_pending(redis, AsyncMock(), "c1")
        redis.xack.assert_awaited_once()
        proc.assert_not_awaited()
        redis.xadd.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_poison_entry_is_dead_lettered(self):
        redis = self._redis([("1-0", {"kind": "result"})])
        with (
            patch.object(
                mod, "_delivery_count", AsyncMock(return_value=mod.MAX_DELIVERIES + 1)
            ),
            patch.object(mod, "_process_entry", AsyncMock()) as proc,
        ):
            await mod._reclaim_pending(redis, AsyncMock(), "c1")
        # Moved to the dead-letter stream, ACKed, and NOT re-processed.
        assert redis.xadd.await_args.args[0] == mod.DEAD_STREAM
        redis.xack.assert_awaited_once()
        proc.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_normal_entry_processed_and_acked(self):
        redis = self._redis([("1-0", {"kind": "result"})])
        with (
            patch.object(mod, "_delivery_count", AsyncMock(return_value=1)),
            patch.object(mod, "_process_entry", AsyncMock(return_value=True)) as proc,
        ):
            await mod._reclaim_pending(redis, AsyncMock(), "c1")
        proc.assert_awaited_once()
        redis.xack.assert_awaited_once()
        redis.xadd.assert_not_awaited()  # not dead-lettered

    @pytest.mark.asyncio
    async def test_failed_process_is_not_acked(self):
        redis = self._redis([("1-0", {"kind": "result"})])
        with (
            patch.object(mod, "_delivery_count", AsyncMock(return_value=1)),
            patch.object(mod, "_process_entry", AsyncMock(return_value=False)),
        ):
            await mod._reclaim_pending(redis, AsyncMock(), "c1")
        # A retryable failure must stay in the PEL (no ACK) for redelivery.
        redis.xack.assert_not_awaited()


class TestWalkCoreDependents:
    def _node(self, nid, queue, dependents=None, canceled=False):
        return SimpleNamespace(
            id=nid,
            queue=queue,
            dependents=dependents or [],
            job_status=(mod.JobStatus.CANCELED if canceled else "finished"),
        )

    def test_yields_core_skips_storage(self):
        core = self._node("c", "core")
        storage = self._node("s", "storage.poolA.high")
        root = self._node("r", "core", dependents=[core, storage])
        got = [d.id for d in mod._walk_core_dependents(root)]
        assert got == ["c"]  # storage member not yielded

    def test_recurses_through_core(self):
        leaf = self._node("c2", "core")
        mid = self._node("c1", "core", dependents=[leaf])
        root = self._node("r", "core", dependents=[mid])
        got = [d.id for d in mod._walk_core_dependents(root)]
        assert got == ["c1", "c2"]

    def test_cycle_is_safe(self):
        a = self._node("a", "core")
        b = self._node("b", "core", dependents=[a])
        a.dependents = [b]  # a <-> b cycle
        root = self._node("r", "core", dependents=[a])
        got = [d.id for d in mod._walk_core_dependents(root)]
        # visited guard: each node yielded at most once, no infinite loop.
        assert sorted(got) == ["a", "b"]

    def test_recurses_through_canceled_storage(self):
        core_finalizer = self._node("fin", "core")
        canceled_storage = self._node(
            "cs", "storage.poolA.high", dependents=[core_finalizer], canceled=True
        )
        root = self._node("r", "core", dependents=[canceled_storage])
        # Without the flag the canceled storage member blocks the finalizer...
        assert [d.id for d in mod._walk_core_dependents(root)] == []
        # ...with it, we reach the core finalizer behind it (but never the
        # storage member itself).
        got = [
            d.id for d in mod._walk_core_dependents(root, include_canceled_storage=True)
        ]
        assert got == ["fin"]
