# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for RecycleBinService — delegates to common helpers and
queues async deletes. Tests pin the not-found dispatch + the queue
enqueue payload shape.
"""

from unittest.mock import AsyncMock, patch

import pytest
from api.services.error import Error
from api.services.recycle_bin import RecycleBinService


class TestGetUserCutoffTime:
    @patch(
        "api.services.recycle_bin.RecycleBinHelpers.get_category_recycle_bin_cuttoff_time",
        return_value=86400,
    )
    @patch("api.services.recycle_bin.RethinkCategory.exists", return_value=True)
    def test_returns_helper_value(self, _exists, mock_get):
        assert RecycleBinService.get_user_cutoff_time("default") == 86400
        mock_get.assert_called_once_with(category_id="default")

    @patch("api.services.recycle_bin.RethinkCategory.exists", return_value=False)
    def test_raises_not_found_for_missing_category(self, _exists):
        with pytest.raises(Error):
            RecycleBinService.get_user_cutoff_time("ghost")


class TestGetRecycleBinEntryDetails:
    @patch(
        "api.services.recycle_bin.RecycleBinHelpers.get",
        return_value={"id": "rb1", "items": []},
    )
    @patch("api.services.recycle_bin.RethinkRecycleBin.exists", return_value=True)
    def test_forwards_all_data_flag(self, _exists, mock_get):
        RecycleBinService.get_recycle_bin_entry_details("rb1", all_data=True)
        mock_get.assert_called_once_with(recycle_bin_id="rb1", all_data=True)

    @patch("api.services.recycle_bin.RethinkRecycleBin.exists", return_value=False)
    def test_raises_not_found(self, _exists):
        with pytest.raises(Error):
            RecycleBinService.get_recycle_bin_entry_details("ghost")


class TestRestoreRecycleBinEntry:
    @patch("api.services.recycle_bin.CommonRecycleBin")
    @patch("api.services.recycle_bin.RethinkRecycleBin.exists", return_value=True)
    def test_calls_restore_on_common(self, _exists, mock_common):
        instance = mock_common.return_value
        instance.restore.return_value = "restore-task-1"
        result = RecycleBinService.restore_recycle_bin_entry("rb1")
        mock_common.assert_called_once_with("rb1")
        instance.restore.assert_called_once_with()
        assert result == "restore-task-1"

    @patch("api.services.recycle_bin.RethinkRecycleBin.exists", return_value=False)
    def test_raises_not_found(self, _exists):
        with pytest.raises(Error):
            RecycleBinService.restore_recycle_bin_entry("ghost")


class TestBulkRestore:
    """Commit 695852b09 wraps the sync per-item restore loop in
    ``asyncio.to_thread`` so the asyncio event loop stays free during
    a multi-item restore. The service is fire-and-forget: it returns
    the IDs immediately and the actual work happens in a background
    task. Pin both halves of the contract.
    """

    async def test_returns_ids_immediately(self):
        """``bulk_restore`` must NOT block on the per-item work — it
        returns the ID list synchronously after scheduling the task."""
        with patch("api.services.recycle_bin.CommonRecycleBin"):
            ids = ["rb-1", "rb-2", "rb-3"]
            result = await RecycleBinService.bulk_restore(ids, "u-1")
            assert result == ids

    async def test_schedules_work_via_create_task(self, monkeypatch):
        """The work goes through ``asyncio.create_task(asyncio.to_thread(...))``.
        Pin so a refactor that drops the create_task / to_thread wrap
        and runs the loop body inline (which would block the event
        loop on every restore) fails this test."""
        import asyncio as _asyncio

        captured = {}
        original_create_task = _asyncio.create_task

        def spy_create_task(coro_or_future, *args, **kwargs):
            captured["scheduled"] = True
            return original_create_task(coro_or_future, *args, **kwargs)

        monkeypatch.setattr("asyncio.create_task", spy_create_task)
        with patch("api.services.recycle_bin.CommonRecycleBin"):
            await RecycleBinService.bulk_restore(["rb-1"], "u-1")
        assert captured.get("scheduled") is True

    async def test_empty_ids_still_returns_list(self):
        """Edge case: empty ID list must still succeed (no work to do)."""
        result = await RecycleBinService.bulk_restore([], "u-1")
        assert result == []


class TestDeleteRecycleBinEntry:
    @patch("api.services.recycle_bin.RethinkUser.exists", return_value=True)
    @patch("api.services.recycle_bin.RethinkRecycleBin.exists", return_value=True)
    async def test_enqueues_delete_action(self, _rb, _user):
        with patch("api.services.recycle_bin.RecycleBinDeleteQueue") as mock_q:
            instance = mock_q.return_value
            instance.enqueue = AsyncMock()
            await RecycleBinService.delete_recycle_bin_entry("rb1", "u1")
            instance.enqueue.assert_awaited_once_with(
                {"action": "delete", "recycle_bin_id": "rb1", "user_id": "u1"}
            )

    @patch("api.services.recycle_bin.RethinkRecycleBin.exists", return_value=False)
    async def test_raises_not_found_for_missing_entry(self, _rb):
        with pytest.raises(Error):
            await RecycleBinService.delete_recycle_bin_entry("ghost", "u1")

    @patch("api.services.recycle_bin.RethinkUser.exists", return_value=False)
    @patch("api.services.recycle_bin.RethinkRecycleBin.exists", return_value=True)
    async def test_raises_not_found_for_missing_user(self, _rb, _user):
        with pytest.raises(Error):
            await RecycleBinService.delete_recycle_bin_entry("rb1", "ghost")
