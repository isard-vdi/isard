#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``ConsolidateProcessed``."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.usage import consolidate as mod

    mod._domains_cache.clear()

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.ConsolidateProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.ConsolidateProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    yield {
        "mock_table": mock_table,
        "mod": mod,
        "Processed": mod.ConsolidateProcessed,
    }


class TestInsertConsumptionBatch:
    def test_calls_insert_with_data_and_options(self, stub_rdb):
        stub_rdb["mock_table"].return_value.insert.return_value.run.return_value = {
            "inserted": 2
        }
        data = [{"pk": "1"}, {"pk": "2"}]
        result = stub_rdb["Processed"].insert_consumption_batch(data)
        assert result == {"inserted": 2}
        stub_rdb["mock_table"].assert_any_call("usage_consumption")
        stub_rdb["mock_table"].return_value.insert.assert_called_with(
            data, conflict="update", durability="soft"
        )


class TestGetDomainsWithTags:
    def test_returns_grouped_domain_data(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.pluck.return_value.group.return_value.run.return_value = {
            "d1": [{"id": "d1", "name": "Desktop", "tag": "t1", "tag_name": "T1"}]
        }
        result = stub_rdb["Processed"].get_domains_with_tags()
        assert result == {
            "d1": [{"id": "d1", "name": "Desktop", "tag": "t1", "tag_name": "T1"}]
        }
        stub_rdb["mock_table"].assert_any_call("domains")


class TestClearGetDomainsWithTagsCache:
    def test_clears_cache(self, stub_rdb):
        mod = stub_rdb["mod"]
        mod._domains_cache["k"] = {"x": 1}
        stub_rdb["Processed"].clear_get_domains_with_tags_cache()
        assert len(mod._domains_cache) == 0
