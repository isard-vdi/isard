#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``StatsProcessed`` top-level summaries."""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.stale_while_revalidate import (
    KeyedStaleWhileRevalidate,
    StaleWhileRevalidate,
)

# Which module-global cache backs which method. Used by the wiring tests below
# so a cache swapped onto the wrong method fails instead of silently
# cross-serving another method's value.
CACHE_OF_METHOD = {
    "get_users_stats": lambda mod: mod._users_stats_cache,
    "get_desktops_stats": lambda mod: mod._desktops_stats_cache,
    "get_templates_stats": lambda mod: mod._templates_stats_cache,
    "get_domains_status": lambda mod: mod._domains_status_cache,
    "get_categories_deployments": lambda mod: mod._categories_deployments_cache,
    "get_domains_by_category_count": lambda mod: mod._domains_by_category_cache,
    "get_group_by_categories": lambda mod: mod._group_by_categories_cache,
}


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

    def clear_all():
        mod.StatsProcessed.clear_get_users_stats_cache()
        mod.StatsProcessed.clear_get_desktops_stats_cache()
        mod.StatsProcessed.clear_get_templates_stats_cache()
        mod.StatsProcessed.clear_get_domains_status_cache()
        mod.StatsProcessed.clear_get_kind_cache()
        mod.StatsProcessed.clear_get_categories_deployments_cache()
        mod.StatsProcessed.clear_get_domains_by_category_count_cache()
        mod.StatsProcessed.clear_get_group_by_categories_cache()

    # The caches are module globals: clear on the way in so a prior test can't
    # leak a value into this one, and on the way out so a stubbed MagicMock
    # never survives into another module's tests.
    clear_all()
    yield {"mock_table": mock_table, "Processed": mod.StatsProcessed, "mod": mod}
    clear_all()


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


def _both_desktop_chains(chain):
    """Stub every query shape this method has used, so the assertions below pin
    the OUTPUT and not the query that produced it — that is what must not change
    when the query is retuned."""
    chain.get_all.return_value.count.return_value.run.return_value = 7
    chain.get_all.return_value.group.return_value.count.return_value.run.return_value = {
        "Started": 3,
        "Stopped": 4,
    }
    chain.group.return_value.count.return_value.run.return_value = {
        ("desktop", "Started"): 3,
        ("desktop", "Stopped"): 4,
        ("template", "Stopped"): 2,
    }
    chain.between.return_value.group.return_value.count.return_value.run.return_value = {
        "Started": 3,
        "Stopped": 4,
    }


class TestGetDesktopsStats:
    def test_returns_total_and_status_breakdown(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        _both_desktop_chains(chain)
        result = stub_rdb["Processed"].get_desktops_stats()
        assert result == {"total": 7, "status": {"Started": 3, "Stopped": 4}}
        stub_rdb["mock_table"].assert_any_call("domains")

    def test_reads_domains_once(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        _both_desktop_chains(chain)
        stub_rdb["Processed"].get_desktops_stats()
        runs = [call for call in chain.mock_calls if call[0].endswith("run")]
        assert len(runs) == 1


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

    @pytest.mark.parametrize(
        "getter, clearer",
        [
            ("get_desktops_stats", "clear_get_desktops_stats_cache"),
            ("get_templates_stats", "clear_get_templates_stats_cache"),
            ("get_domains_status", "clear_get_domains_status_cache"),
            ("get_categories_deployments", "clear_get_categories_deployments_cache"),
            (
                "get_domains_by_category_count",
                "clear_get_domains_by_category_count_cache",
            ),
            ("get_group_by_categories", "clear_get_group_by_categories_cache"),
        ],
    )
    def test_every_cached_method_has_a_working_invalidator(
        self, stub_rdb, getter, clearer
    ):
        cache = CACHE_OF_METHOD[getter](stub_rdb["mod"])
        getattr(stub_rdb["Processed"], getter)()
        assert cache.currsize == 1
        getattr(stub_rdb["Processed"], clearer)()
        assert cache.currsize == 0

    def test_get_kind_invalidator_drops_every_bucket(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.pluck.return_value.run.return_value = []
        chain.pluck.return_value.run.return_value = []
        stub_rdb["Processed"].get_kind("desktops")
        stub_rdb["Processed"].get_kind("hypervisors")
        assert stub_rdb["mod"]._kind_cache.currsize == 2
        stub_rdb["Processed"].clear_get_kind_cache()
        assert stub_rdb["mod"]._kind_cache.currsize == 0


class TestCacheWiring:
    """The cache objects themselves — mixing them up is silent and expensive."""

    def test_every_stats_cache_is_a_distinct_object(self, stub_rdb):
        caches = [get(stub_rdb["mod"]) for get in CACHE_OF_METHOD.values()]
        caches.append(stub_rdb["mod"]._kind_cache)
        assert len({id(cache) for cache in caches}) == len(caches)

    def test_no_stats_cache_makes_a_caller_wait_for_a_refresh(self, stub_rdb):
        """Every stats cache must be stale-while-revalidate, not plain TTL.

        A TTL cache turns each expiry into a blocking miss with no
        single-flight, which is what these endpoints cannot afford.
        """
        caches = [get(stub_rdb["mod"]) for get in CACHE_OF_METHOD.values()]
        caches.append(stub_rdb["mod"]._kind_cache)
        assert all(
            isinstance(cache, (StaleWhileRevalidate, KeyedStaleWhileRevalidate))
            for cache in caches
        )

    # Which driver each cache answers to. The periods are constants in the
    # module, read off this repository — never a number derived from one
    # installation's traffic, which is how a TTL calibrated against a poll
    # period that does not exist gets shipped behind a passing test.
    COLLECTOR_DRIVEN = [
        "_domains_status_cache",
        "_kind_cache",
        "_categories_deployments_cache",
        "_group_by_categories_cache",
    ]
    PANEL_DRIVEN = ["_desktops_stats_cache", "_domains_by_category_cache"]

    @pytest.mark.parametrize(
        "cache_name, driver_attr",
        [(name, "_COLLECTOR_SCRAPE_S") for name in COLLECTOR_DRIVEN]
        + [(name, "_ADMIN_PANEL_POLL_S") for name in PANEL_DRIVEN],
    )
    def test_ttl_is_no_longer_than_its_caller_s_interval(
        self, stub_rdb, cache_name, driver_attr
    ):
        """Serve data as fresh as the caller's cadence allows, and no older.

        A TTL longer than the interval does not make the refreshes cheaper —
        while it is at or below the period there is one refresh per poll either
        way — it only hands out older numbers. Parallel consumers are absorbed
        by the single-flight refresh, not by a long TTL.
        """
        mod = stub_rdb["mod"]
        cache = getattr(mod, cache_name)
        interval = getattr(mod, driver_attr)
        assert cache.ttl <= interval, (
            f"{cache_name} ttl={cache.ttl}s exceeds its caller's {interval}s "
            "interval, so it serves data older than it needs to"
        )

    def test_the_two_panel_caches_cannot_disagree(self, stub_rdb):
        """Both render on the same screen; different TTLs means visible drift."""
        mod = stub_rdb["mod"]
        ttls = {getattr(mod, name).ttl for name in self.PANEL_DRIVEN}
        assert len(ttls) == 1, f"panel caches would drift apart: {ttls}"


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

    def test_unknown_kind_caches_nothing_and_still_raises_next_time(self, stub_rdb):
        from isardvdi_common.helpers.error_base import ErrorBase

        for _ in range(3):
            with pytest.raises(ErrorBase):
                stub_rdb["Processed"].get_kind("widgets")
        assert stub_rdb["mod"]._kind_cache.currsize == 0

    def test_each_kind_gets_its_own_bucket(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.get_all.return_value.pluck.return_value.run.return_value = [
            {"id": "d1", "user": "u1"}
        ]
        chain.pluck.return_value.run.return_value = [
            {"id": "h1", "status": "Online", "only_forced": False}
        ]
        desktops = stub_rdb["Processed"].get_kind("desktops")
        hypervisors = stub_rdb["Processed"].get_kind("hypervisors")
        assert desktops == [{"id": "d1", "user": "u1"}]
        assert hypervisors == [{"id": "h1", "status": "Online", "only_forced": False}]
        assert stub_rdb["mod"]._kind_cache.currsize == 2

    def test_second_call_for_a_kind_is_served_from_cache(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        run = chain.get_all.return_value.pluck.return_value.run
        run.return_value = [{"id": "d1", "user": "u1"}]
        for _ in range(4):
            stub_rdb["Processed"].get_kind("desktops")
        assert run.call_count == 1


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


def _consistent_domain_counts(chain, fold):
    """Feed both query shapes from one truth: the whole-table fold, and the
    desktop-range fold that is its ``desktop`` half. The two endpoints ask
    different questions of the same data, so a test that stubs them
    independently could not catch them disagreeing."""
    chain.group.return_value.count.return_value.run.return_value = fold
    chain.between.return_value.group.return_value.count.return_value.run.return_value = {
        status: n for (kind, status), n in fold.items() if kind == "desktop"
    }


class TestDesktopsTotalMatchesTheStatusFold:
    """``total`` and the per-status breakdown must not be able to disagree."""

    def test_total_is_the_sum_of_the_statuses(self, stub_rdb):
        _consistent_domain_counts(
            stub_rdb["mock_table"].return_value,
            {
                ("desktop", "Started"): 4,
                ("desktop", "Stopped"): 11,
                ("template", "Stopped"): 2,
            },
        )
        result = stub_rdb["Processed"].get_desktops_stats()
        assert result["total"] == 15
        assert result["total"] == sum(result["status"].values())

    def test_it_reports_the_same_desktop_numbers_as_domains_status(self, stub_rdb):
        """The two endpoints now run different queries; they must still agree."""
        _consistent_domain_counts(
            stub_rdb["mock_table"].return_value,
            {("desktop", "Started"): 4, ("desktop", "Failed"): 1},
        )
        desktops = stub_rdb["Processed"].get_desktops_stats()
        stub_rdb["Processed"].clear_get_domains_status_cache()
        domains = stub_rdb["Processed"].get_domains_status()
        assert desktops["status"] == domains["desktop"]


class TestEveryCacheHasAStalenessCeiling:
    """A frozen dashboard must eventually say so instead of lying quietly."""

    def test_no_stats_cache_serves_an_unbounded_stale_value(self, stub_rdb):
        caches = [get(stub_rdb["mod"]) for get in CACHE_OF_METHOD.values()]
        caches.append(stub_rdb["mod"]._kind_cache)
        missing = [cache.name for cache in caches if cache.max_stale is None]
        assert not missing, f"caches with no staleness ceiling: {missing}"

    @pytest.mark.parametrize("cache_name", TestCacheWiring.COLLECTOR_DRIVEN)
    def test_the_ceiling_leaves_room_for_several_refresh_attempts(
        self, stub_rdb, cache_name
    ):
        """Too tight a ceiling would fail the endpoint on a single hiccup."""
        cache = getattr(stub_rdb["mod"], cache_name)
        assert cache.max_stale >= 3 * cache.ttl
