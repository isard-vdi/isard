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


class TestGetGeneralStats:
    def test_composes_three_summaries(self, stub_rdb, monkeypatch):
        monkeypatch.setattr(
            stub_rdb["Processed"], "get_users_stats", classmethod(lambda cls: {"u": 1})
        )
        monkeypatch.setattr(
            stub_rdb["Processed"],
            "get_desktops_stats",
            classmethod(lambda cls: {"d": 2}),
        )
        monkeypatch.setattr(
            stub_rdb["Processed"],
            "get_templates_stats",
            classmethod(lambda cls: {"t": 3}),
        )
        result = stub_rdb["Processed"].get_general_stats()
        assert result == {
            "users": {"u": 1},
            "desktops": {"d": 2},
            "templates": {"t": 3},
        }


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


class TestGetCategoryStatus:
    def test_filters_stable_desktops_and_stopped_templates(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        # desktops: cat-a Started (filtered), cat-a Unknown (kept).
        # templates: cat-a Stopped (filtered), cat-b Failed (kept).
        chain.get_all.return_value.pluck.return_value.group.return_value.count.return_value.run.side_effect = [
            {("cat-a", "Started"): 5, ("cat-a", "Unknown"): 2},
            {("cat-a", "Stopped"): 7, ("cat-b", "Failed"): 1},
        ]
        result = stub_rdb["Processed"].get_category_status()
        assert result["cat-a"] == {"desktops_wrong_status": {"Unknown": 2}}
        assert result["cat-b"] == {"templates_wrong_status": {"Failed": 1}}


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


class TestGetCategoriesKindState:
    def test_desktop_no_state_returns_full_breakdown(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.pluck.return_value.__getitem__.return_value.run.return_value = ["cat-a"]
        chain.get_all.return_value.count.return_value.run.return_value = 5
        chain.get_all.return_value.filter.return_value.count.return_value.run.return_value = (
            2
        )
        result = stub_rdb["Processed"].get_categories_kind_state("desktop")
        assert result["cat-a"]["desktops"]["total"] == 5
        assert "Other" in result["cat-a"]["desktops"]["status"]

    def test_template_enabled_returns_just_enabled(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.pluck.return_value.__getitem__.return_value.run.return_value = ["cat-a"]
        chain.get_all.return_value.count.return_value.run.return_value = 9
        result = stub_rdb["Processed"].get_categories_kind_state("template", "enabled")
        assert result["cat-a"]["templates"]["status"]["enabled"] == 9

    def test_unknown_kind_returns_empty(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.pluck.return_value.__getitem__.return_value.run.return_value = ["cat-a"]
        result = stub_rdb["Processed"].get_categories_kind_state("widget")
        assert result == {}


class TestGetCategoriesLimitsHardware:
    def test_with_explicit_limits(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.pluck.return_value.run.return_value = [
            {"id": "cat-a", "limits": {"vcpus": 32, "memory": 64000}}
        ]
        chain.get_all.return_value.count.return_value.run.return_value = 4
        chain.get_all.return_value.__getitem__.return_value.__getitem__.return_value.__getitem__.return_value.sum.return_value.run.return_value = (
            8
        )
        result = stub_rdb["Processed"].get_categories_limits_hardware()
        assert result["cat-a"]["Started desktops"] == 4
        assert result["cat-a"]["vCPUs"]["Limit"] == 32
        assert result["cat-a"]["Memory"]["Limit"] == 64000

    def test_with_limits_false_falls_back_to_zero(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.pluck.return_value.run.return_value = [{"id": "cat-a", "limits": False}]
        chain.get_all.return_value.count.return_value.run.return_value = 0
        chain.get_all.return_value.__getitem__.return_value.__getitem__.return_value.__getitem__.return_value.sum.return_value.run.return_value = (
            0
        )
        result = stub_rdb["Processed"].get_categories_limits_hardware()
        assert result["cat-a"]["vCPUs"]["Limit"] == 0
        assert result["cat-a"]["Memory"]["Limit"] == 0
