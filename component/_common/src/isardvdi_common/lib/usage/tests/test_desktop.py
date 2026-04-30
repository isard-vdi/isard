#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``DesktopUsageProcessed``."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.usage import desktop as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.DesktopUsageProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.DesktopUsageProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    monkeypatch.setattr(mod.r, "branch", lambda *a, **kw: ("BRANCH", a, kw))

    class _Row:
        def __getitem__(self, key):
            return self

        def __le__(self, other):
            return self

        def __lt__(self, other):
            return self

        def __ge__(self, other):
            return self

        def __gt__(self, other):
            return self

        def default(self, *a):
            return self

        def is_empty(self):
            return self

    monkeypatch.setattr(mod.r, "row", _Row())
    yield {"mock_table": mock_table, "Processed": mod.DesktopUsageProcessed}


class TestFetchLogs:
    def test_returns_logs_query_results(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.without.return_value.filter.return_value.merge.return_value.merge.return_value.merge.return_value.run.return_value = [
            {"id": "log-1", "started_time": "x"}
        ]
        day = datetime(2026, 1, 1, tzinfo=timezone.utc)
        day_after = datetime(2026, 1, 2, tzinfo=timezone.utc)
        result = stub_rdb["Processed"].fetch_logs(day, day_after)
        assert result == [{"id": "log-1", "started_time": "x"}]
        stub_rdb["mock_table"].assert_any_call("logs_desktops")
