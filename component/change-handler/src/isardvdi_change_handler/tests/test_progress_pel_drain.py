# SPDX-License-Identifier: AGPL-3.0-or-later

"""``stream:progress`` had no pending-list recovery of its own.

Measured on a live stack before this existed: killing the consumer mid-batch
left 26 entries pending, and they were still 26 after 106 s and a restart.
``_reap_dead_consumers`` correctly refuses a consumer that still holds entries,
so the group also grew one dead member per restart.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from isardvdi_change_handler.streams import task_results_consumer as consumer
from isardvdi_change_handler.streams.trim import PROGRESS_STREAM


def _redis(entries, raises=None):
    fake = MagicMock()
    if raises is not None:
        fake.xautoclaim = AsyncMock(side_effect=raises)
    else:
        fake.xautoclaim = AsyncMock(return_value=["0-0", entries])
    fake.xack = AsyncMock()
    return fake


@pytest.mark.asyncio
class TestDrainingTheProgressPel:
    async def test_it_claims_only_past_the_idle_threshold(self):
        fake = _redis([])
        await consumer._drain_progress_pel(fake, "c1")

        fake.xautoclaim.assert_awaited_once()
        assert fake.xautoclaim.await_args.args[0] == PROGRESS_STREAM
        assert (
            fake.xautoclaim.await_args.kwargs["min_idle_time"]
            == consumer.RECLAIM_IDLE_MS
        )

    async def test_every_claimed_entry_is_acked(self):
        fake = _redis([("1-0", {"kind": "progress"}), ("2-0", {"kind": "progress"})])

        assert await consumer._drain_progress_pel(fake, "c1") == 2
        assert [c.args[2] for c in fake.xack.await_args_list] == ["1-0", "2-0"]
        for call in fake.xack.await_args_list:
            assert call.args[0] == PROGRESS_STREAM

    async def test_a_stale_tick_is_dropped_and_not_re_emitted(self, monkeypatch):
        """Re-emitting it would walk a progress bar backwards."""
        process = AsyncMock()
        monkeypatch.setattr(consumer, "_process_entry", process)
        fake = _redis([("1-0", {"kind": "progress", "progress": "0.1"})])

        await consumer._drain_progress_pel(fake, "c1")

        process.assert_not_awaited()

    async def test_the_drop_is_reported(self, caplog):
        fake = _redis([("1-0", {"kind": "progress"})])
        with caplog.at_level("WARNING"):
            await consumer._drain_progress_pel(fake, "c1")
        assert "stale progress" in caplog.text

    async def test_nothing_pending_says_nothing(self, caplog):
        fake = _redis([])
        with caplog.at_level("WARNING"):
            assert await consumer._drain_progress_pel(fake, "c1") == 0
        assert caplog.text == ""
        fake.xack.assert_not_awaited()

    async def test_a_failure_here_never_stops_the_consumer(self):
        fake = _redis(None, raises=RuntimeError("NOGROUP"))
        assert await consumer._drain_progress_pel(fake, "c1") == 0


class TestTheReclaimTimerDrivesIt:
    def test_run_drains_the_progress_pel_on_the_reclaim_timer(self):
        import ast
        import inspect

        run = ast.parse(inspect.getsource(consumer.run).lstrip()).body[0]
        called = {
            node.func.id
            for node in ast.walk(run)
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
        }
        assert "_drain_progress_pel" in called
        assert "_reclaim_pending" in called

    @pytest.mark.parametrize("stream", ["RESULT_STREAM", "PROGRESS_STREAM"])
    def test_both_streams_get_their_dead_consumers_reaped_on_the_timer(self, stream):
        import ast
        import inspect

        run = ast.parse(inspect.getsource(consumer.run).lstrip()).body[0]
        loop = [n for n in ast.walk(run) if isinstance(n, ast.While)][-1]
        reaped = {
            node.args[1].id
            for node in ast.walk(loop)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "_reap_dead_consumers"
            and len(node.args) > 1
            and isinstance(node.args[1], ast.Name)
        }
        assert stream in reaped
