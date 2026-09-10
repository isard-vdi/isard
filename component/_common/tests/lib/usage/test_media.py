#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``MediaUsageProcessed``."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.usage import media as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.MediaUsageProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.MediaUsageProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    yield {"mock_table": mock_table, "Processed": mod.MediaUsageProcessed}


class TestFetchMedia:
    def test_returns_media_rows(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.pluck.return_value.run.return_value = [
            {"id": "m1", "user": "u1", "progress": {"total_bytes": 1024}}
        ]
        result = stub_rdb["Processed"].fetch_media()
        assert result == [{"id": "m1", "user": "u1", "progress": {"total_bytes": 1024}}]
        stub_rdb["mock_table"].assert_any_call("media")
        stub_rdb["mock_table"].return_value.get_all.assert_called_with(
            "Downloaded", index="status"
        )
