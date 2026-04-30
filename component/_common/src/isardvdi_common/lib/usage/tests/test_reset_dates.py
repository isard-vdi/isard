#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``ResetDatesUsageProcessed``."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.usage import reset_dates as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.ResetDatesUsageProcessed,
        "_rdb_context",
        classmethod(lambda cls: _Ctx()),
    )
    monkeypatch.setattr(
        type(mod.ResetDatesUsageProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)

    class _RowExpr:
        def __getitem__(self, key):
            return self

        def __le__(self, other):
            return self

    monkeypatch.setattr(mod.r, "row", _RowExpr())
    monkeypatch.setattr(mod.r, "desc", lambda x: ("DESC", x))
    yield {"mock_table": mock_table, "Processed": mod.ResetDatesUsageProcessed}


class TestListResetDates:
    def test_returns_ascending_with_window(self, stub_rdb):
        d1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        d2 = datetime(2026, 6, 1, tzinfo=timezone.utc)
        chain = stub_rdb["mock_table"].return_value
        # filter().order_by()["date"].run() returns descending; lib reverses.
        chain.filter.return_value.order_by.return_value.__getitem__.return_value.run.return_value = [
            d2,
            d1,
        ]
        result = stub_rdb["Processed"].list_reset_dates(d1, d2)
        assert result == [d1, d2]

    def test_empty_table_returns_empty_list(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.order_by.return_value.__getitem__.return_value.run.return_value = []
        result = stub_rdb["Processed"].list_reset_dates()
        assert result == []


class TestReplaceResetDates:
    def test_clears_then_inserts_each(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.delete.return_value.run.return_value = {"deleted": 5}
        chain.insert.return_value.run.return_value = {"inserted": 1}
        d1 = datetime(2026, 1, 1, tzinfo=timezone.utc)
        d2 = datetime(2026, 6, 1, tzinfo=timezone.utc)
        stub_rdb["Processed"].replace_reset_dates([d1, d2, d1])  # duplicate filtered
        # 1 delete + 2 inserts (deduplicated set).
        chain.delete.assert_called_once()
        assert chain.insert.call_count == 2
