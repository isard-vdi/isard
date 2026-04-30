#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``ReservablesProcessed`` (tier 3.4 batch 3 — migrated
from apiv4 ``services/reservables.py:update_item``).
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.bookings import reservables as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.ReservablesProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.ReservablesProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    yield {"mock_table": mock_table, "Processed": mod.ReservablesProcessed}


class TestGetItem:
    def test_returns_row_when_present(self, stub_rdb):
        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = {
            "id": "g1",
            "name": "GPU 1",
        }
        result = stub_rdb["Processed"].get_item("gpus", "g1")
        assert result == {"id": "g1", "name": "GPU 1"}
        stub_rdb["mock_table"].assert_any_call("gpus")
        stub_rdb["mock_table"].return_value.get.assert_called_with("g1")

    def test_returns_none_when_missing(self, stub_rdb):
        stub_rdb["mock_table"].return_value.get.return_value.run.return_value = None
        assert stub_rdb["Processed"].get_item("gpus", "missing") is None


class TestNameExistsForOther:
    def test_true_when_match(self, stub_rdb):
        stub_rdb["mock_table"].return_value.filter.return_value.run.return_value = [
            {"id": "other"}
        ]
        assert stub_rdb["Processed"].name_exists_for_other("gpus", "n", "g1") is True
        stub_rdb["mock_table"].assert_any_call("gpus")

    def test_false_when_no_match(self, stub_rdb):
        stub_rdb["mock_table"].return_value.filter.return_value.run.return_value = []
        assert stub_rdb["Processed"].name_exists_for_other("gpus", "n", "g1") is False


class TestUpdateItem:
    def test_calls_update_when_data(self, stub_rdb):
        stub_rdb["Processed"].update_item("gpus", "g1", {"name": "renamed"})
        stub_rdb["mock_table"].return_value.get.assert_called_with("g1")
        stub_rdb["mock_table"].return_value.get.return_value.update.assert_called_with(
            {"name": "renamed"}
        )

    def test_noop_when_empty(self, stub_rdb):
        stub_rdb["Processed"].update_item("gpus", "g1", {})
        stub_rdb["mock_table"].return_value.get.return_value.update.assert_not_called()
