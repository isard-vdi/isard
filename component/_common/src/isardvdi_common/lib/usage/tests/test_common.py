#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``UsageProcessed`` and the module-level usage helpers
(tier 3.4 batch 3 — migrated from apiv4 ``services/usage/common.py``).
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    """Stub the rdb connection on UsageProcessed."""
    from isardvdi_common.lib.usage import common as mod

    # Caches must be cleared between tests; @cached decorators cache
    # results across the whole pytest run otherwise.
    mod._group_name_cache.clear()
    mod._category_name_cache.clear()
    mod._owners_info_cache.clear()
    mod._params_cache.clear()
    mod._params_item_type_custom_cache.clear()

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.UsageProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.UsageProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)
    # r.row / r.args are not auto-intercepted by MagicMock.
    monkeypatch.setattr(mod.r, "args", lambda x: ("ARGS", x))

    # r.row[X] <= Y in production builds a rdb expression; in the
    # stubbed environment we just need it not to TypeError.
    class _RowExpr:
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

        def __eq__(self, other):  # pragma: no cover - rdb expr semantics
            return self

    monkeypatch.setattr(mod.r, "row", _RowExpr())
    yield {"mock_table": mock_table, "mod": mod, "Processed": mod.UsageProcessed}


class TestGetGroupName:
    def test_returns_group_name(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.return_value = {
            "name": "infra"
        }
        assert stub_rdb["Processed"].get_group_name("g1") == "infra"
        stub_rdb["mock_table"].assert_any_call("groups")

    def test_returns_deleted_on_missing(self, stub_rdb):
        from rethinkdb.errors import ReqlNonExistenceError

        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.side_effect = ReqlNonExistenceError(
            "no such row", None, None
        )
        assert stub_rdb["Processed"].get_group_name("missing") == "[DELETED]"


class TestGetCategoryName:
    def test_returns_category_name(self, stub_rdb):
        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.return_value = {
            "name": "Default"
        }
        assert stub_rdb["Processed"].get_category_name("c1") == "Default"
        stub_rdb["mock_table"].assert_any_call("categories")

    def test_returns_deleted_on_missing(self, stub_rdb):
        from rethinkdb.errors import ReqlNonExistenceError

        stub_rdb[
            "mock_table"
        ].return_value.get.return_value.pluck.return_value.run.side_effect = ReqlNonExistenceError(
            "no such row", None, None
        )
        assert stub_rdb["Processed"].get_category_name("missing") == "[DELETED]"


class TestGetOwnersInfo:
    def test_builds_owner_info_for_each_user(self, stub_rdb, monkeypatch):
        users = [
            {"id": "u1", "name": "alice", "group": "g1", "category": "c1"},
            {"id": "u2", "name": "bob", "group": "g1", "category": "c2"},
        ]
        stub_rdb["mock_table"].return_value.pluck.return_value.run.return_value = users

        # Stub the dependent classmethods so the @cached decorators
        # don't tangle with the parent test (cache key includes ``cls``).
        monkeypatch.setattr(
            stub_rdb["Processed"],
            "get_group_name",
            classmethod(lambda cls, gid: f"{gid}-name"),
        )
        monkeypatch.setattr(
            stub_rdb["Processed"],
            "get_category_name",
            classmethod(lambda cls, cid: f"{cid}-name"),
        )

        result = stub_rdb["Processed"].get_owners_info()
        assert result["u1"]["owner_user_name"] == "alice"
        assert result["u1"]["owner_group_id"] == "g1"
        assert result["u1"]["owner_group_name"] == "g1-name"
        assert result["u2"]["owner_category_name"] == "c2-name"


class TestGetAbsConsumptions:
    def test_runs_aggregation(self, stub_rdb):
        from datetime import datetime, timezone

        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.filter.return_value.group.return_value.max.return_value.ungroup.return_value.map.return_value.coerce_to.return_value.run.return_value = {
            "i1##desktop": {"hours": 1}
        }
        date = datetime.now(tz=timezone.utc)
        result = stub_rdb["Processed"].get_abs_consumptions("desktop", date)
        assert result == {"i1##desktop": {"hours": 1}}
        stub_rdb["mock_table"].assert_any_call("usage_consumption")


class TestGetParams:
    def test_returns_param_groupings(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.group.return_value.ungroup.return_value.map.return_value.coerce_to.return_value.run.return_value = {
            "desktop": [{"id": "p1"}]
        }
        result = stub_rdb["Processed"].get_params()
        assert result == {"desktop": [{"id": "p1"}]}
        stub_rdb["mock_table"].assert_any_call("usage_parameter")


class TestGetDefaultConsumption:
    def test_returns_id_to_default_map(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.run.return_value = [
            {"id": "p1", "default": 1.0},
            {"id": "p2", "default": 2.5},
        ]
        result = stub_rdb["Processed"].get_default_consumption()
        assert result == {"p1": 1.0, "p2": 2.5}

    def test_filters_by_ids_when_provided(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.run.return_value = [{"id": "p1", "default": 1.0}]
        result = stub_rdb["Processed"].get_default_consumption(["p1"])
        assert result == {"p1": 1.0}


class TestGetParamsItemTypeCustom:
    def test_returns_filtered_rows(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.run.return_value = [
            {"id": "p_custom", "item_type": "desktop", "custom": True}
        ]
        result = stub_rdb["Processed"].get_params_item_type_custom("desktop", True)
        assert result == [{"id": "p_custom", "item_type": "desktop", "custom": True}]


class TestClearAllCaches:
    def test_clears_every_cache(self, stub_rdb):
        mod = stub_rdb["mod"]
        mod._group_name_cache["g1"] = "x"
        mod._category_name_cache["c1"] = "x"
        mod._owners_info_cache["k"] = {}
        mod._params_cache["k"] = {}
        mod._params_item_type_custom_cache["k"] = []
        stub_rdb["Processed"].clear_all_caches()
        assert len(mod._group_name_cache) == 0
        assert len(mod._category_name_cache) == 0
        assert len(mod._owners_info_cache) == 0
        assert len(mod._params_cache) == 0
        assert len(mod._params_item_type_custom_cache) == 0


class TestGetOwnerInfo:
    def test_returns_owner_info_when_known(self, monkeypatch):
        from isardvdi_common.lib.usage import common as mod

        monkeypatch.setattr(
            mod.UsageProcessed,
            "get_owners_info",
            classmethod(
                lambda cls: {
                    "u1": {
                        "owner_user_id": "u1",
                        "owner_user_name": "alice",
                        "owner_group_id": "g1",
                        "owner_group_name": "infra",
                        "owner_category_id": "c1",
                        "owner_category_name": "default",
                    }
                }
            ),
        )
        result = mod.get_owner_info("u1")
        assert result["owner_user_name"] == "alice"

    def test_returns_placeholder_when_unknown(self, monkeypatch):
        from isardvdi_common.lib.usage import common as mod

        monkeypatch.setattr(
            mod.UsageProcessed,
            "get_owners_info",
            classmethod(lambda cls: {}),
        )
        result = mod.get_owner_info("orphan")
        assert result["owner_user_id"] == "orphan"
        assert result["owner_user_name"] == "[DELETED]"
        assert result["owner_group_id"] == "[USER DELETED]"


class TestSecurizeFormulaEvaluation:
    def test_simple_arithmetic(self):
        from isardvdi_common.lib.usage.common import securize_eval

        # Constants only; no Name lookups.
        assert securize_eval("1 + 2 * 3", {}) == 7

    def test_variable_substitution(self):
        from isardvdi_common.lib.usage.common import securize_eval

        result = securize_eval("a + b", {"a": 1, "b": 2})
        assert result == 3

    def test_rejects_attribute_access(self):
        from isardvdi_common.lib.usage.common import securize_eval

        with pytest.raises(ValueError):
            securize_eval("a.b", {"a": object()})

    def test_rejects_subscript(self):
        from isardvdi_common.lib.usage.common import securize_eval

        with pytest.raises(ValueError):
            securize_eval("a[0]", {"a": [1]})
