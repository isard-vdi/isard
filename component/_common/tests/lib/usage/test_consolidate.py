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

    def test_large_batch_is_inserted_in_chunks(self, stub_rdb):
        insert = stub_rdb["mock_table"].return_value.insert
        insert.return_value.run.return_value = {"inserted": 1, "errors": 0}
        data = [{"pk": str(i)} for i in range(2500)]

        result = stub_rdb["Processed"].insert_consumption_batch(data)

        sent = [call.args[0] for call in insert.call_args_list]
        assert [len(chunk) for chunk in sent] == [1000, 1000, 500]
        assert [row for chunk in sent for row in chunk] == data
        assert result == {"inserted": 3, "errors": 0}

    def test_peak_memory_does_not_grow_with_the_batch(self, monkeypatch):
        """The driver builds one query object per value, so the peak of a
        single insert grows with the batch; chunking keeps it flat."""
        import tracemalloc

        from isardvdi_common.lib.usage import consolidate as mod

        class _Ctx:
            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class _Conn:
            def _start(self, term, **opts):
                term.build()
                return {"inserted": 0}

        monkeypatch.setattr(
            mod.ConsolidateProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
        )
        monkeypatch.setattr(
            type(mod.ConsolidateProcessed),
            "_rdb_connection",
            property(lambda self: _Conn()),
        )

        def peak(rows):
            data = [
                {
                    "pk": str(i),
                    "item_id": "item-%d" % i,
                    "inc": {"dsk_hours": 1.5, "dsk_starts": 1},
                    "abs": {"dsk_hours": 10.5, "dsk_starts": 7},
                }
                for i in range(rows)
            ]
            tracemalloc.start()
            mod.ConsolidateProcessed.insert_consumption_batch(data)
            _, top = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            return top

        assert peak(20000) < 3 * peak(2000)


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
