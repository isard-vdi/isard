# SPDX-License-Identifier: AGPL-3.0-or-later

"""The delete queue reaching an entry that the cascade of another entry already deleted."""

import asyncio
import logging
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers import recycle_bin as mod


class _Entry:
    def __init__(self, status, error=None):
        self.status = status
        self.item_type = "desktop"
        self.delete_storage = MagicMock(side_effect=error)


@pytest.fixture
def queue(monkeypatch):
    q = mod.RecycleBinDeleteQueue.__new__(mod.RecycleBinDeleteQueue)
    update = MagicMock(name="update_status")
    revert = MagicMock(name="revert_to_recycled")
    monkeypatch.setattr(mod.Helpers, "update_status", update)
    monkeypatch.setattr(mod.Helpers, "revert_to_recycled", revert, raising=False)
    return q, update, revert


def test_an_entry_already_deleted_is_left_alone(queue, monkeypatch, caplog):
    q, update, revert = queue
    entry = _Entry("deleted")
    monkeypatch.setattr(mod, "RecycleBin", lambda id: entry)

    with caplog.at_level(logging.ERROR):
        asyncio.run(q.perform_operation("rb-1", "u-1"))

    entry.delete_storage.assert_not_called()
    update.assert_not_called()
    revert.assert_not_called()
    assert not [r for r in caplog.records if r.levelno >= logging.ERROR]


def test_a_failed_delete_is_logged_with_its_reason_and_reverted(
    queue, monkeypatch, caplog
):
    q, update, revert = queue
    error = mod.Error(
        "precondition_required", "Cannot delete entry with status restored"
    )
    entry = _Entry("queued", error=error)
    monkeypatch.setattr(mod, "RecycleBin", lambda id: entry)

    with caplog.at_level(logging.ERROR):
        asyncio.run(q.perform_operation("rb-2", "u-1"))

    assert any(
        "Cannot delete entry with status restored" in r.getMessage()
        for r in caplog.records
    )
    update.assert_not_called()
    revert.assert_called_once_with("rb-2")
