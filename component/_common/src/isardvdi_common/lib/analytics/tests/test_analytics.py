#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``AnalyticsProcessed``."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.analytics import analytics as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.AnalyticsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.AnalyticsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", x))
    monkeypatch.setattr(mod.r, "expr", lambda x: ("EXPR", x))
    monkeypatch.setattr(mod.r, "branch", lambda *a: ("BRANCH", a))
    monkeypatch.setattr(mod.r, "desc", lambda x: ("DESC", x))
    monkeypatch.setattr(mod.r, "now", lambda: ("NOW",))
    monkeypatch.setattr(mod.r, "epoch_time", lambda x: ("EPOCH", x))

    class _RowExpr:
        def __getitem__(self, key):
            return self

        def __le__(self, other):
            return self

        def __lt__(self, other):
            return self

        def __eq__(self, other):  # pragma: no cover - rdb expr semantics
            return self

        def __ne__(self, other):  # pragma: no cover
            return self

        def __and__(self, other):
            return self

        def __or__(self, other):
            return self

        def __invert__(self):
            return self

        def ne(self, other):
            return self

    monkeypatch.setattr(mod.r, "row", _RowExpr())
    yield {"mock_table": mock_table, "Processed": mod.AnalyticsProcessed, "mod": mod}


class TestStorageUsage:
    def test_returns_media_and_domains_in_gib(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        # Without categories: media -> filter().pluck().sum() -> bytes
        # then divided by 1073741824 = 1 GiB.
        chain.filter.return_value.pluck.return_value.sum.return_value.run.return_value = (
            1073741824
        )
        chain.pluck.return_value.merge.return_value.sum.return_value.run.return_value = (
            2147483648  # 2 GiB
        )
        result = stub_rdb["Processed"].storage_usage()
        assert result["media"] == 1.0
        # The /1073741824 is wrapped in the rdb chain so the .run() returns
        # the already-divided value; the lib code wraps an extra division
        # for the categories branch only. Without categories, the rdb does it.

    def test_with_categories_uses_index(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.filter.return_value.pluck.return_value.sum.return_value.run.return_value = (
            10737418240  # /10737418240 = 1.0
        )
        chain.get_all.return_value.pluck.return_value.merge.return_value.sum.return_value.run.return_value = (
            1073741824
        )
        result = stub_rdb["Processed"].storage_usage(["c-a"])
        assert result["media"] == 1.0


class TestResourceCount:
    def test_returns_six_buckets(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.count.return_value.run.return_value = 5
        chain.filter.return_value.count.return_value.run.return_value = 3
        chain.count.return_value.run.return_value = 10
        result = stub_rdb["Processed"].resource_count()
        # All six keys present.
        assert set(result.keys()) == {
            "desktops",
            "templates",
            "media",
            "users",
            "groups",
            "deployments",
        }


class TestGraphConfigCRUD:
    def test_get_graph_config_returns_row(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.run.return_value = {"id": "g1", "name": "MyGraph"}
        assert stub_rdb["Processed"].get_graph_config("g1") == {
            "id": "g1",
            "name": "MyGraph",
        }

    def test_get_graph_config_missing_raises_not_found(self, stub_rdb):
        from isardvdi_common.helpers.error_base import ErrorBase

        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.run.return_value = None
        with pytest.raises(ErrorBase):
            stub_rdb["Processed"].get_graph_config("missing")

    def test_create_graph_config_inserts(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.insert.return_value.run.return_value = {"inserted": 1}
        stub_rdb["Processed"].create_graph_config({"id": "g1", "name": "x"})
        chain.insert.assert_called_once()

    def test_update_graph_config_targets_id(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.update.return_value.run.return_value = {"replaced": 1}
        stub_rdb["Processed"].update_graph_config("g1", {"name": "renamed"})
        chain.get.assert_called_with("g1")

    def test_delete_graph_config_targets_id(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.delete.return_value.run.return_value = {"deleted": 1}
        stub_rdb["Processed"].delete_graph_config("g1")
        chain.get.assert_called_with("g1")

    def test_list_graph_configs_returns_rows(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.merge.return_value.run.return_value = [{"id": "g1"}, {"id": "g2"}]
        result = stub_rdb["Processed"].list_graph_configs()
        assert {row["id"] for row in result} == {"g1", "g2"}


class TestEchartHelpers:
    def test_get_daily_items(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.group.return_value.count.return_value.run.return_value = {
            (2026, 1, 1): 5,
            (2026, 1, 2): 3,
        }
        result = stub_rdb["Processed"].get_daily_items("desktops", "started_time")
        assert result["series"]["started_time"] == [5, 3] or result["series"][
            "started_time"
        ] == [3, 5]
        assert len(result["x"]) == 2

    def test_get_grouped_data_uses_index_when_available(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        # First call: index_list returns ["status"]
        chain.index_list.return_value.run.return_value = ["status"]
        # Second call: query.count().run() returns the grouped counts
        chain.group.return_value.count.return_value.run.return_value = {
            "Started": 4,
            "Stopped": 1,
            None: 2,  # filtered out
        }
        result = stub_rdb["Processed"].get_grouped_data("domains", "status")
        names = {r["name"] for r in result}
        assert "Started" in names
        assert None not in names

    def test_get_grouped_unique_data_runs(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.index_list.return_value.run.return_value = []
        chain.group.return_value.map.return_value.distinct.return_value.count.return_value.run.return_value = {
            "user-a": 3
        }
        result = stub_rdb["Processed"].get_grouped_unique_data(
            "logs_desktops", "starting_by", "user_id"
        )
        assert result == [{"value": 3, "name": "user-a"}]

    def test_get_nested_array_grouped_data_runs(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.concat_map.return_value.group.return_value.count.return_value.run.return_value = {
            "rdp": 3,
            "spice": 2,
        }
        result = stub_rdb["Processed"].get_nested_array_grouped_data(
            "domains", "viewers", "kind"
        )
        names = {r["name"] for r in result}
        assert names == {"rdp", "spice"}


class TestSuggestedRemovals:
    def test_combines_empty_deployments_and_unused_desktops(
        self, stub_rdb, monkeypatch
    ):
        monkeypatch.setattr(
            stub_rdb["Processed"],
            "get_empty_deployments",
            classmethod(lambda cls, categories=None: [{"id": "d1"}]),
        )
        monkeypatch.setattr(
            stub_rdb["Processed"],
            "get_unused_desktops",
            classmethod(
                lambda cls, months_without_use=6, categories=None: {
                    "size": 5,
                    "desktops": [],
                }
            ),
        )
        result = stub_rdb["Processed"].suggested_removals()
        assert result["empty_deployments"][0]["id"] == "d1"
        assert result["unused_desktops"]["size"] == 5
