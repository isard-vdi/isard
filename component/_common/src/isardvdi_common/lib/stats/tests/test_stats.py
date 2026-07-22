#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``StatsProcessed`` top-level summaries."""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def stub_rdb(monkeypatch):
    from isardvdi_common.lib.stats import stats as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.StatsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.StatsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)

    # Each cached method must start with a fresh cache so prior tests
    # don't leak return values into this one.
    mod.StatsProcessed.clear_get_users_stats_cache()
    mod.StatsProcessed.clear_get_desktops_stats_cache()
    mod.StatsProcessed.clear_get_templates_stats_cache()
    mod.StatsProcessed.clear_get_domains_status_cache()

    yield {"mock_table": mock_table, "Processed": mod.StatsProcessed, "mod": mod}


class TestGetUsersStats:
    def test_returns_total_status_and_roles(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.count.return_value.run.return_value = 12
        chain.get_all.return_value.count.return_value.run.return_value = 9
        chain.group.return_value.count.return_value.run.return_value = {
            "admin": 1,
            "user": 11,
        }
        result = stub_rdb["Processed"].get_users_stats()
        assert result == {
            "total": 12,
            "status": {"enabled": 9, "disabled": 3},
            "roles": {"admin": 1, "user": 11},
        }
        stub_rdb["mock_table"].assert_any_call("users")


class TestGetDesktopsStats:
    def test_returns_total_and_status_breakdown(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        # First call: total. Second call: grouped count.
        chain.get_all.return_value.count.return_value.run.return_value = 7
        chain.get_all.return_value.group.return_value.count.return_value.run.return_value = {
            "Started": 3,
            "Stopped": 4,
        }
        result = stub_rdb["Processed"].get_desktops_stats()
        assert result == {"total": 7, "status": {"Started": 3, "Stopped": 4}}
        stub_rdb["mock_table"].assert_any_call("domains")


class TestGetTemplatesStats:
    def test_counts_enabled_and_treats_missing_as_disabled(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.pluck.return_value.run.return_value = [
            {"enabled": True},
            {"enabled": False},
            {},  # legacy row without ``enabled`` — counts as disabled
        ]
        result = stub_rdb["Processed"].get_templates_stats()
        assert result == {"total": 3, "enabled": 1, "disabled": 2}


class TestGetDomainsStatus:
    def test_folds_grouped_kind_status_cursor(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.group.return_value.count.return_value.run.return_value = {
            ("desktop", "Started"): 4,
            ("desktop", "Stopped"): 1,
            ("template", "Stopped"): 2,
        }
        result = stub_rdb["Processed"].get_domains_status()
        assert result == {
            "desktop": {"Started": 4, "Stopped": 1},
            "template": {"Stopped": 2},
        }

    def test_unknown_kind_creates_bucket(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.group.return_value.count.return_value.run.return_value = {
            ("unexpected", "Foo"): 1,
        }
        result = stub_rdb["Processed"].get_domains_status()
        assert result["unexpected"] == {"Foo": 1}
        assert result["desktop"] == {}
        assert result["template"] == {}


class TestCacheInvalidators:
    def test_clear_users_stats_cache_drops_entry(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.count.return_value.run.return_value = 1
        chain.get_all.return_value.count.return_value.run.return_value = 1
        chain.group.return_value.count.return_value.run.return_value = {}
        stub_rdb["Processed"].get_users_stats()
        assert stub_rdb["mod"]._users_stats_cache.currsize == 1
        stub_rdb["Processed"].clear_get_users_stats_cache()
        assert stub_rdb["mod"]._users_stats_cache.currsize == 0


class TestGetKind:
    def test_desktops_pluck_id_user(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.pluck.return_value.run.return_value = [
            {"id": "d1", "user": "u1"}
        ]
        result = stub_rdb["Processed"].get_kind("desktops")
        assert result == [{"id": "d1", "user": "u1"}]
        chain.get_all.assert_any_call("desktop", index="kind")

    def test_users_pluck_id_role_category_group(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.pluck.return_value.run.return_value = [
            {"id": "u1", "role": "admin", "category": "c1", "group": "g1"}
        ]
        result = stub_rdb["Processed"].get_kind("users")
        assert result[0]["role"] == "admin"
        stub_rdb["mock_table"].assert_any_call("users")

    def test_hypervisors_pluck_id_status_only_forced(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.pluck.return_value.run.return_value = [
            {"id": "h1", "status": "Online", "only_forced": False}
        ]
        result = stub_rdb["Processed"].get_kind("hypervisors")
        assert result[0]["id"] == "h1"
        stub_rdb["mock_table"].assert_any_call("hypervisors")

    def test_unknown_kind_raises_bad_request(self, stub_rdb):
        from isardvdi_common.helpers.error_base import ErrorBase

        with pytest.raises(ErrorBase) as exc:
            stub_rdb["Processed"].get_kind("widgets")
        assert "widgets" in str(exc.value)


class TestGetCategoriesDeployments:
    def test_groups_deployments_by_category(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.merge.return_value.group.return_value.count.return_value.run.return_value = {
            "cat-a": 3,
            "cat-b": 1,
        }
        result = stub_rdb["Processed"].get_categories_deployments()
        assert result == {"cat-a": 3, "cat-b": 1}
        stub_rdb["mock_table"].assert_any_call("deployments")


class TestGetDomainsByCategoryCount:
    def test_returns_per_category_status_breakdown(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.pluck.return_value.group.return_value.count.return_value.ungroup.return_value.map.return_value.group.return_value.ungroup.return_value.map.return_value.run.return_value = [
            {"category": "cat-a", "category_name": "Cat A", "desktops": {"Started": 4}},
        ]
        result = stub_rdb["Processed"].get_domains_by_category_count()
        assert result[0]["category"] == "cat-a"
        assert result[0]["desktops"] == {"Started": 4}


class TestGetGroupByCategories:
    def test_assembles_per_category_summary(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        # categories list (.pluck("id")["id"].run())
        chain.pluck.return_value.__getitem__.return_value.run.return_value = ["cat-a"]
        # Every per-category count returns 1; roles return a stub dict.
        chain.get_all.return_value.count.return_value.run.return_value = 1
        chain.get_all.return_value.filter.return_value.count.return_value.run.return_value = (
            1
        )
        chain.get_all.return_value.group.return_value.count.return_value.run.return_value = {
            "admin": 1
        }
        result = stub_rdb["Processed"].get_group_by_categories()
        assert "cat-a" in result
        assert result["cat-a"]["users"]["total"] == 1
        assert result["cat-a"]["users"]["status"] == {"enabled": 1, "disabled": 0}
        assert result["cat-a"]["desktops"]["total"] == 1
        assert result["cat-a"]["templates"]["total"] == 1

    def test_drops_none_role_keys(self, stub_rdb):
        # A user with role=None produces a None key from .group("role")
        # which Pydantic's strict StatsCategoriesResponse rejects with
        # `Input should be a valid string`. Reproducer for bug 55: the
        # aggregation dict must not contain None keys.
        chain = stub_rdb["mock_table"].return_value
        chain.pluck.return_value.__getitem__.return_value.run.return_value = ["cat-a"]
        chain.get_all.return_value.count.return_value.run.return_value = 2
        chain.get_all.return_value.filter.return_value.count.return_value.run.return_value = (
            1
        )
        chain.get_all.return_value.group.return_value.count.return_value.run.return_value = {
            "admin": 1,
            None: 1,
        }
        result = stub_rdb["Processed"].get_group_by_categories()
        assert result["cat-a"]["users"]["roles"] == {"admin": 1}
        assert None not in result["cat-a"]["users"]["roles"]
