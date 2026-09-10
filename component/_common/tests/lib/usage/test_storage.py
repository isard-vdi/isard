#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``StorageUsageProcessed``."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.usage import storage as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.StorageUsageProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.StorageUsageProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", x))

    class _Row:
        def __getitem__(self, key):
            return self

    monkeypatch.setattr(mod.r, "row", _Row())
    yield {"mock_table": mock_table, "Processed": mod.StorageUsageProcessed}


class TestFetchStorages:
    def test_returns_storage_rows(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.pluck.return_value.merge.return_value.run.return_value = [
            {"id": "s1", "user_id": "u1", "qemu-img-info": {"actual-size": 100}}
        ]
        result = stub_rdb["Processed"].fetch_storages()
        assert result[0]["id"] == "s1"
        stub_rdb["mock_table"].assert_any_call("storage")
