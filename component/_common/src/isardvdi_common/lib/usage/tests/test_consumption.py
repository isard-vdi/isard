#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``ConsumptionUsageProcessed`` + module-level helpers."""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.usage import consumption as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.ConsumptionUsageProcessed,
        "_rdb_context",
        classmethod(lambda cls: _Ctx()),
    )
    monkeypatch.setattr(
        type(mod.ConsumptionUsageProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", x))

    class _RowExpr:
        def __getitem__(self, key):
            return self

        def __le__(self, other):
            return self

        def __eq__(self, other):  # pragma: no cover - rdb expr semantics
            return self

        def __and__(self, other):
            return self

        def ne(self, other):
            return self

    monkeypatch.setattr(mod.r, "row", _RowExpr())
    monkeypatch.setattr(mod.r, "branch", lambda *a: None)
    yield {
        "mock_table": mock_table,
        "Processed": mod.ConsumptionUsageProcessed,
        "mod": mod,
    }


class TestSubtractDicts:
    def test_subtracts_numeric_leaves(self):
        from isardvdi_common.lib.usage.consumption import subtract_dicts

        result = subtract_dicts({"a": 10, "b": 5}, {"a": 3, "b": 2})
        assert result == {"a": 7, "b": 3}

    def test_recurses_into_nested_dicts(self):
        from isardvdi_common.lib.usage.consumption import subtract_dicts

        result = subtract_dicts(
            {"top": {"x": 10}, "scalar": 5}, {"top": {"x": 4}, "scalar": 1}
        )
        assert result == {"top": {"x": 6}, "scalar": 4}

    def test_treats_missing_dict2_keys_as_zero(self):
        from isardvdi_common.lib.usage.consumption import subtract_dicts

        assert subtract_dicts({"a": 5}, {}) == {"a": 5}

    def test_keeps_non_numeric_leaves_unchanged(self):
        from isardvdi_common.lib.usage.consumption import subtract_dicts

        assert subtract_dicts({"name": "foo"}, {"name": "bar"}) == {"name": "foo"}


class TestListDistinctItems:
    def test_returns_full_table_when_no_filter(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.pluck.return_value.distinct.return_value.run.return_value = [
            {"item_id": "i1", "item_name": "n1"},
        ]
        result = stub_rdb["Processed"].list_distinct_items()
        assert result[0]["item_id"] == "i1"

    def test_filters_by_ids(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.pluck.return_value.distinct.return_value.run.return_value = [
            {"item_id": "i2", "item_name": "n2"},
        ]
        result = stub_rdb["Processed"].list_distinct_items(["i2"])
        assert result[0]["item_id"] == "i2"
        chain.get_all.assert_called_once_with(("ARGS", ["i2"]), index="item_id")


class TestListDistinctItemsByConsumer:
    def test_no_category_basic_pluck(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.pluck.return_value.distinct.return_value.run.return_value = [
            {"item_id": "i1", "item_name": "n1"},
        ]
        result = stub_rdb["Processed"].list_distinct_items_by_consumer("desktop")
        assert result[0]["item_id"] == "i1"
        chain.get_all.assert_called_with("desktop", index="item_consumer")

    def test_with_category_filter(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.pluck.return_value.filter.return_value.distinct.return_value.run.return_value = [
            {"item_id": "i1", "item_name": "n1", "item_consumer_category_id": "c-a"},
        ]
        result = stub_rdb["Processed"].list_distinct_items_by_consumer("desktop", "c-a")
        assert result[0]["item_consumer_category_id"] == "c-a"


class TestGetItemDateConsumption:
    def test_falls_back_to_default_when_no_row(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        # The .pluck("id").run() inside _zero_consumption returns parameters
        chain.pluck.return_value.run.return_value = [{"id": "p1"}, {"id": "p2"}]
        # The first .filter().order_by().nth().default().run() returns the default
        chain.get_all.return_value.pluck.return_value.filter.return_value.order_by.return_value.nth.return_value.default.return_value.run.return_value = {
            "name": "n1",
            "date": datetime(2026, 1, 1, tzinfo=timezone.utc),
            "abs": {"p1": 0, "p2": 0},
            "inc": {"p1": 0, "p2": 0},
            "item_id": "i1",
            "item_type": "desktop",
        }
        # The second .nth(0).default()["inc"].run() returns inc
        chain.get_all.return_value.pluck.return_value.filter.return_value.nth.return_value.default.return_value.__getitem__.return_value.run.return_value = {
            "p1": 0,
            "p2": 0,
        }
        result = stub_rdb["Processed"].get_item_date_consumption(
            datetime(2026, 1, 1, tzinfo=timezone.utc), "i1", "desktop", "n1"
        )
        assert result["item_id"] == "i1"


class TestGetCategoryDescription:
    def test_returns_description(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get.return_value.default.return_value.__getitem__.return_value.run.return_value = (
            "Default category"
        )
        result = stub_rdb["Processed"].get_category_description("c1")
        assert result == "Default category"
