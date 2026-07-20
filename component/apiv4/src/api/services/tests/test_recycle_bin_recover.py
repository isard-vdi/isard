# SPDX-License-Identifier: AGPL-3.0-or-later

"""RecycleBinService stuck-delete recovery (admin manual recovery).

Pins that ``recover_stuck_entries`` re-enqueues exactly the ids the helper
reports as stuck (``deleting``/``queued``), via the same ``RecycleBinDeleteQueue``
the normal delete path uses, and that ``list_stuck_entries`` is a thin delegate.
"""

from unittest.mock import AsyncMock, patch

import pytest
from api.services.recycle_bin import RecycleBinService


class TestListStuckEntries:
    @patch(
        "api.services.recycle_bin.RecycleBinHelpers.get_stuck_delete_entries",
        return_value=[{"id": "rb-1", "status": "deleting"}],
    )
    def test_delegates_to_helper(self, mock_get):
        result = RecycleBinService.list_stuck_entries(older_than_minutes=15)
        assert result == [{"id": "rb-1", "status": "deleting"}]
        mock_get.assert_called_once_with(older_than_minutes=15)


class TestRecoverStuckEntries:
    @pytest.mark.asyncio
    async def test_enqueues_each_stuck_id(self, monkeypatch):
        created = []
        # Capture the scheduled coroutine WITHOUT scheduling it, then await
        # it deterministically (no sleep-based flakiness).
        monkeypatch.setattr(
            "asyncio.create_task", lambda coro, *a, **k: created.append(coro)
        )

        with patch(
            "api.services.recycle_bin.RecycleBinHelpers.get_stuck_delete_entries",
            return_value=[{"id": "rb-1"}, {"id": "rb-2"}],
        ), patch("api.services.recycle_bin.RecycleBinDeleteQueue") as mock_q:
            instance = mock_q.return_value
            instance.enqueue = AsyncMock()

            ids = await RecycleBinService.recover_stuck_entries("admin-1")
            assert ids == ["rb-1", "rb-2"]

            for coro in created:
                await coro

            assert instance.enqueue.await_count == 2
            instance.enqueue.assert_any_await(
                {"action": "delete", "recycle_bin_id": "rb-1", "user_id": "admin-1"}
            )
            instance.enqueue.assert_any_await(
                {"action": "delete", "recycle_bin_id": "rb-2", "user_id": "admin-1"}
            )

    @pytest.mark.asyncio
    async def test_no_stuck_entries_returns_empty(self, monkeypatch):
        monkeypatch.setattr("asyncio.create_task", lambda coro, *a, **k: coro.close())
        with patch(
            "api.services.recycle_bin.RecycleBinHelpers.get_stuck_delete_entries",
            return_value=[],
        ), patch("api.services.recycle_bin.RecycleBinDeleteQueue") as mock_q:
            instance = mock_q.return_value
            instance.enqueue = AsyncMock()
            ids = await RecycleBinService.recover_stuck_entries("admin-1")
            assert ids == []
            instance.enqueue.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_forwards_age_threshold_to_helper(self, monkeypatch):
        monkeypatch.setattr("asyncio.create_task", lambda coro, *a, **k: coro.close())
        with patch(
            "api.services.recycle_bin.RecycleBinHelpers.get_stuck_delete_entries",
            return_value=[],
        ) as mock_get, patch("api.services.recycle_bin.RecycleBinDeleteQueue"):
            await RecycleBinService.recover_stuck_entries(
                "admin-1", older_than_minutes=45
            )
            mock_get.assert_called_once_with(older_than_minutes=45)
