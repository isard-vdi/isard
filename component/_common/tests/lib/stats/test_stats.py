#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``StatsProcessed`` top-level summaries."""

import json
from contextlib import nullcontext
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.stale_while_revalidate import (
    KeyedStaleWhileRevalidate,
    StaleWhileRevalidate,
)
from rethinkdb.ast import ReQLDecoder

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
        + [
            # The status summary is the graph, and the operator can ask for it
            # every second, so it must keep up with the fastest interval the
            # selector offers.
            ("_desktops_stats_cache", "_ADMIN_PANEL_MIN_POLL_S"),
            # The per-category table deliberately does not follow a 1 s
            # selection — see the comment beside its cache — so it is held to
            # the default interval instead.
            ("_domains_by_category_cache", "_ADMIN_PANEL_POLL_S"),
        ],
    )
    def test_ttl_is_below_its_caller_s_interval(
        self, stub_rdb, cache_name, driver_attr
    ):
        """Serve data as fresh as the caller's cadence allows, and no older.

        Strictly below it: an entry ages from the end of its fetch, so a TTL
        equal to the interval refreshes only on every other poll. Parallel
        consumers are absorbed by the single-flight refresh, not by a long TTL.
        """
        mod = stub_rdb["mod"]
        cache = getattr(mod, cache_name)
        interval = getattr(mod, driver_attr)
        assert cache.ttl < interval, (
            f"{cache_name} ttl={cache.ttl}s exceeds its caller's {interval}s "
            "interval, so it serves data older than it needs to"
        )

    def test_the_graph_is_the_freshest_thing_on_the_panel(self, stub_rdb):
        """The two panel caches diverge on purpose, in one direction only.

        The status summary is what the operator watches move, so it must never
        be staler than the table beside it. The reverse would be a bug: a graph
        lagging behind its own category breakdown.
        """
        mod = stub_rdb["mod"]
        assert mod._desktops_stats_cache.ttl <= mod._domains_by_category_cache.ttl


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

    def test_hypervisors_pluck_the_degraded_state(self, stub_rdb):
        chain = stub_rdb["mock_table"].return_value
        chain.pluck.return_value.run.return_value = []
        stub_rdb["Processed"].get_kind("hypervisors")
        assert {"degraded": ["is_degraded", "reason"]} in chain.pluck.call_args.args

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


def _category_folds(chain, categories, users, desktops=None, templates=None):
    """Feed ``get_group_by_categories`` its four queries: the category ids, the
    whole-table users fold, and one fold per kind range of ``kind_category``.
    Both domain folds share the mocked chain, so the range picks the fold."""
    chain.pluck.return_value.__getitem__.return_value.run.return_value = categories
    chain.group.return_value.count.return_value.run.return_value = users
    folds = {"desktop": desktops or {}, "template": templates or {}}

    def between(lower, upper, index):
        assert index == "kind_category"
        selection = MagicMock(name=f"between:{lower[0]}")
        selection.group.return_value.count.return_value.run.return_value = folds[
            lower[0]
        ]
        return selection

    chain.between.side_effect = between


class _Field:
    """``doc["x"]`` inside a group key. ReQL's ``eq`` compares by type, so
    ``1`` is not ``true``."""

    def __init__(self, value):
        self.value = value

    def eq(self, other):
        return type(self.value) is type(other) and self.value == other


class _Row:
    def __init__(self, doc):
        self.doc = doc

    def __getitem__(self, field):
        if field not in self.doc:
            raise KeyError(field)
        return _Field(self.doc[field])


def _branch(*args):
    *pairs, default = args
    for condition, value in zip(pairs[::2], pairs[1::2]):
        if condition:
            return value
    return default


def _server_group(docs, keys):
    """Group ``docs`` as the server does, keys compared as JSON so ``1`` and
    ``true`` are separate groups, then decode the pairs with the driver's own
    GROUPED_DATA conversion, which keys them in a dict where they are not."""
    groups = {}
    for doc in docs:
        key = []
        for k in keys:
            try:
                key.append(doc.get(k) if isinstance(k, str) else k(_Row(doc)))
            except KeyError:  # a non-existence error groups as null
                key.append(None)
        groups.setdefault(json.dumps(key), [key, 0])[1] += 1
    return ReQLDecoder.convert_grouped_data({"data": list(groups.values())})


def _category_documents(chain, categories, users, domains):
    """Like ``_category_folds``, but the folds are computed from documents
    with the keys the query actually asks for."""
    chain.pluck.return_value.__getitem__.return_value.run.return_value = categories

    def grouped(docs):
        def group(*keys):
            selection = MagicMock(name="group")
            selection.count.return_value.run.return_value = _server_group(docs, keys)
            return selection

        return group

    chain.group.side_effect = grouped(users)

    def between(lower, upper, index):
        assert index == "kind_category"
        selection = MagicMock(name=f"between:{lower[0]}")
        selection.group.side_effect = grouped(
            [d for d in domains if d.get("kind") == lower[0] and "category" in d]
        )
        return selection

    chain.between.side_effect = between


class TestGetGroupByCategories:
    def test_assembles_per_category_summary(self, stub_rdb):
        _category_folds(
            stub_rdb["mock_table"].return_value,
            ["cat-a", "cat-empty"],
            {
                ("cat-a", "admin", True): 1,
                ("cat-a", "user", True): 2,
                ("cat-a", "user", False): 1,
                ("cat-a", "user", None): 1,
                # Rows of a deleted category, and of none at all.
                ("cat-gone", "user", True): 5,
                (None, "user", True): 3,
            },
            {
                ("cat-a", "Started"): 2,
                ("cat-a", "Stopped"): 3,
                ("cat-a", "Unknown"): 1,
                ("cat-a", "Downloading"): 1,
                ("cat-a", None): 1,
                ("cat-gone", "Started"): 4,
            },
            {
                ("cat-a", True): 2,
                ("cat-a", False): 1,
                ("cat-a", None): 1,
                ("cat-gone", True): 7,
            },
        )
        result = stub_rdb["Processed"].get_group_by_categories()
        assert result["cat-a"] == {
            "users": {
                "total": 5,
                "status": {"enabled": 3, "disabled": 2},
                "roles": {"admin": 1, "user": 4},
            },
            "desktops": {
                "total": 8,
                "status": {
                    "Started": 2,
                    "Stopped": 3,
                    "Failed": 0,
                    "Unknown": 0,
                    "Other": 3,
                },
            },
            "templates": {"total": 4, "status": {"enabled": 2, "disabled": 1}},
        }
        # The key set is the categories table: an empty category stays,
        # zero-filled, or its series goes stale; a deleted one never appears.
        assert set(result) == {"cat-a", "cat-empty"}
        assert result["cat-empty"] == {
            "users": {"total": 0, "status": {"enabled": 0, "disabled": 0}, "roles": {}},
            "desktops": {
                "total": 0,
                "status": {
                    "Started": 0,
                    "Stopped": 0,
                    "Failed": 0,
                    "Unknown": 0,
                    "Other": 0,
                },
            },
            "templates": {"total": 0, "status": {"enabled": 0, "disabled": 0}},
        }

    def test_drops_none_role_keys(self, stub_rdb):
        # A user with role=None produces a None key from .group("role")
        # which Pydantic's strict StatsCategoriesResponse rejects with
        # `Input should be a valid string`. Reproducer for bug 55: the
        # aggregation dict must not contain None keys.
        _category_folds(
            stub_rdb["mock_table"].return_value,
            ["cat-a"],
            {
                ("cat-a", "admin", True): 1,
                ("cat-a", None, True): 1,
                ("cat-a", "", False): 1,
            },
        )
        result = stub_rdb["Processed"].get_group_by_categories()
        assert result["cat-a"]["users"]["roles"] == {"admin": 1}
        assert None not in result["cat-a"]["users"]["roles"]
        # Dropped from the roles, still counted as users.
        assert result["cat-a"]["users"]["total"] == 3
        assert result["cat-a"]["users"]["status"] == {"enabled": 2, "disabled": 1}

    def test_numeric_flags_do_not_collapse_their_boolean_group(
        self, stub_rdb, monkeypatch
    ):
        # The driver keys grouped results in a dict, where 1 == True and
        # 0 == False. Grouped on the raw field, one ``active=1`` user
        # overwrote its whole (category, role, True) group: a category of
        # 8 978 users was reported as 1 315.
        monkeypatch.setattr(stub_rdb["mod"].r, "branch", _branch)
        users = [
            {"category": "cat-a", "role": "user", "active": True},
            {"category": "cat-a", "role": "user", "active": True},
            {"category": "cat-a", "role": "user", "active": True},
            {"category": "cat-a", "role": "user", "active": 1},
        ]
        templates = [
            {"kind": "template", "category": "cat-a", "enabled": enabled}
            for enabled in (True, 1, 0)
        ]
        _category_documents(
            stub_rdb["mock_table"].return_value, ["cat-a"], users, templates
        )
        result = stub_rdb["Processed"].get_group_by_categories()
        # Only a boolean true is enabled, as the per-category filter and the
        # ``template_enabled_category`` counts always had it.
        assert result["cat-a"]["users"]["total"] == 4
        assert result["cat-a"]["users"]["status"] == {"enabled": 3, "disabled": 1}
        assert result["cat-a"]["users"]["roles"] == {"user": 4}
        assert result["cat-a"]["templates"] == {
            "total": 3,
            "status": {"enabled": 1, "disabled": 0},
        }


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


def _utc(*args):
    return datetime(*args, tzinfo=timezone.utc)


class _FixedDatetime(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 11, 23, 12, tzinfo=tz)


class _FakeTable:
    """In-memory stand-in for the ReQL selections that read user documents."""

    def __init__(self, rows):
        self.rows = rows

    def get_all(self, keys, index="id"):
        keys = keys if isinstance(keys, tuple) else (keys,)
        assert None not in keys, "RethinkDB refuses null keys"
        if index == "id":
            return _FakeTable([row for row in self.rows if row["id"] in keys])
        assert index == "user"
        return _FakeTable(
            [row for row in self.rows if {u["id"] for u in row["users"]} & set(keys)]
        )

    def filter(self, fields):
        return _FakeTable(
            [row for row in self.rows if fields.items() <= row.items()],
        )

    def pluck(self, *fields):
        return _FakeTable(
            [{f: row[f] for f in fields if f in row} for row in self.rows]
        )

    def concat_map(self, func):
        return _FakeTable(
            [
                item
                for row in self.rows
                for item in func({"users": _FakeTable(row["users"])}).rows
            ]
        )

    def __getitem__(self, field):
        return _FakeTable([row[field] for row in self.rows])

    def run(self, _connection):
        return list(self.rows)


def _logged_user(owner, *roles, deleted=False, category="cat-a"):
    return {
        "owner_user_id": owner,
        "roles": list(roles or ("user",)),
        "deleted": deleted,
        "category": category,
    }


def _started_desktop(
    desktop_id,
    owner,
    *,
    gpu=False,
    deployment_id=None,
    deleted=False,
    server=False,
    category="cat-a",
):
    return {
        "desktop_id": desktop_id,
        "owner_user_id": owner,
        "gpu": gpu,
        "deployment_ids": [deployment_id] if deployment_id else [],
        "deleted": deleted,
        "server": server,
        "category": category,
    }


@pytest.fixture
def monthly_usage(monkeypatch):
    """Call ``get_monthly_usage`` at 2026-11-23 12:00 UTC over the given log
    rows, ``users`` documents and recycle bin entries."""
    from isardvdi_common.lib.stats import stats as mod

    Processed = mod.StatsProcessed

    def call(
        *, logged_users=(), started_desktops=(), users=(), recycle_bin=(), **filters
    ):
        tables = {
            "users": _FakeTable(list(users)),
            "recycle_bin": _FakeTable(list(recycle_bin)),
        }

        def reader(rows):
            return classmethod(
                lambda cls, start, end, category: [
                    dict(row) for row in rows if category in (None, row["category"])
                ]
            )

        monkeypatch.setattr(mod, "datetime", _FixedDatetime)
        monkeypatch.setattr(mod.r, "table", tables.__getitem__)
        monkeypatch.setattr(mod.r, "args", tuple)
        monkeypatch.setattr(
            Processed, "_rdb_context", classmethod(lambda cls: nullcontext())
        )
        monkeypatch.setattr(
            type(Processed), "_rdb_connection", property(lambda self: None)
        )
        monkeypatch.setattr(Processed, "_monthly_users", reader(logged_users))
        monkeypatch.setattr(Processed, "_monthly_desktops", reader(started_desktops))
        monkeypatch.setattr(
            Processed,
            "_monthly_deployments",
            classmethod(lambda cls, ids: {"total": len(ids), "gpu": 0, "deleted": 0}),
        )
        return Processed.get_monthly_usage(**filters)

    return call


class TestGetMonthlyUsagePeriod:
    @pytest.mark.parametrize(
        "month",
        [pytest.param(None, id="omitted"), pytest.param("2026-11", id="current")],
    )
    def test_period_runs_from_the_first_until_now(self, monthly_usage, month):
        usage = monthly_usage(month=month)

        assert usage["period"] == {
            "start": _utc(2026, 11, 1),
            "end": _utc(2026, 11, 23, 12),
        }

    @pytest.mark.parametrize(
        "month, start, end",
        [
            pytest.param(
                "2026-10", _utc(2026, 10, 1), _utc(2026, 11, 1), id="previous-month"
            ),
            pytest.param(
                "2025-12", _utc(2025, 12, 1), _utc(2026, 1, 1), id="year-rollover"
            ),
            pytest.param(
                "2024-02", _utc(2024, 2, 1), _utc(2024, 3, 1), id="leap-february"
            ),
        ],
    )
    def test_period_is_the_whole_month_when_month_is_past(
        self, monthly_usage, month, start, end
    ):
        usage = monthly_usage(month=month)

        assert usage["period"] == {"start": start, "end": end}

    def test_future_month_is_rejected(self, monthly_usage):
        from isardvdi_common.helpers.error_base import ErrorBase

        with pytest.raises(ErrorBase, match="2026-12 is in the future") as exc:
            monthly_usage(month="2026-12")

        assert exc.value.status_code == 400


class TestGetMonthlyUsageUsers:
    def test_users_count_once_each(self, monthly_usage):
        usage = monthly_usage(
            logged_users=[
                _logged_user("u1", "user"),
                _logged_user("u2", "manager"),
                _logged_user("gone", "advanced", deleted=True),
            ]
        )

        assert usage["users"] == {
            "total": 3,
            "by_role": {"manager": 1, "advanced": 1, "user": 1},
            "deleted": 1,
        }

    def test_user_counts_in_every_role_they_had_when_their_role_changed(
        self, monthly_usage
    ):
        usage = monthly_usage(logged_users=[_logged_user("u1", "user", "manager")])

        assert usage["users"] == {
            "total": 1,
            "by_role": {"manager": 1, "advanced": 0, "user": 1},
            "deleted": 0,
        }


class TestGetMonthlyUsageDesktops:
    def test_desktops_count_by_flag(self, monthly_usage):
        usage = monthly_usage(
            started_desktops=[
                _started_desktop("plain", "u1"),
                _started_desktop("gpu", "u1", gpu=True),
                _started_desktop("server", "u1", server=True),
                _started_desktop("deployed", "u1", deployment_id="dep"),
                _started_desktop("gone", "u1", deleted=True),
            ]
        )

        assert usage["desktops"] == {
            "total": 5,
            "gpu": 1,
            "servers": 1,
            "from_deployments": 1,
            "deleted": 1,
        }

    def test_desktop_counts_once_when_its_owner_changed(self, monthly_usage):
        usage = monthly_usage(
            started_desktops=[
                _started_desktop("d1", "u1"),
                _started_desktop("d1", "u2"),
            ]
        )

        assert usage["desktops"]["total"] == 1

    def test_desktop_keeps_the_gpu_and_deployment_of_any_of_its_owners(
        self, monthly_usage
    ):
        usage = monthly_usage(
            started_desktops=[
                _started_desktop("d1", "u1"),
                _started_desktop("d1", "u2", gpu=True, deployment_id="dep"),
                _started_desktop("d1", "u3"),
            ]
        )

        assert usage["desktops"] == {
            "total": 1,
            "gpu": 1,
            "servers": 0,
            "from_deployments": 1,
            "deleted": 0,
        }

    def test_deployments_count_once_each(self, monthly_usage):
        usage = monthly_usage(
            started_desktops=[
                _started_desktop("d1", "u1", deployment_id="dep-a"),
                _started_desktop("d2", "u2", deployment_id="dep-a"),
                _started_desktop("d3", "u3", deployment_id="dep-b"),
                _started_desktop("d4", "u4"),
            ]
        )

        assert usage["deployments"]["total"] == 2

    def test_deployments_include_every_one_a_desktop_was_started_in(
        self, monthly_usage
    ):
        usage = monthly_usage(
            started_desktops=[
                _started_desktop("d1", "u1", deployment_id="dep-a"),
                _started_desktop("d1", "u2", deployment_id="dep-b"),
            ]
        )

        assert usage["deployments"]["total"] == 2
        assert usage["desktops"]["from_deployments"] == 1


class TestGetMonthlyUsageFilters:
    LDAP = {"id": "ldap-user", "provider": "ldap"}
    SAML = {"id": "saml-user", "provider": "saml"}

    def test_category_narrows_users_and_desktops(self, monthly_usage):
        usage = monthly_usage(
            category="cat-a",
            logged_users=[
                _logged_user("u1", category="cat-a"),
                _logged_user("u2", category="cat-b"),
            ],
            started_desktops=[
                _started_desktop("d1", "u1", category="cat-a"),
                _started_desktop("d2", "u2", category="cat-b"),
                _started_desktop("d3", "u2", category="cat-b"),
            ],
        )

        assert usage["users"]["total"] == 1
        assert usage["desktops"]["total"] == 1

    def test_provider_narrows_every_figure(self, monthly_usage):
        usage = monthly_usage(
            provider="ldap",
            users=[self.LDAP, self.SAML],
            logged_users=[_logged_user("ldap-user"), _logged_user("saml-user")],
            started_desktops=[
                _started_desktop("d1", "ldap-user", deployment_id="dep-a"),
                _started_desktop("d2", "saml-user", gpu=True, deployment_id="dep-b"),
                _started_desktop("d3", "saml-user", deleted=True),
            ],
        )

        assert usage["users"]["total"] == 1
        assert usage["desktops"] == {
            "total": 1,
            "gpu": 0,
            "servers": 0,
            "from_deployments": 1,
            "deleted": 0,
        }
        assert usage["deployments"]["total"] == 1

    def test_provider_leaves_out_deleted_users_and_what_they_used(self, monthly_usage):
        usage = monthly_usage(
            provider="ldap",
            users=[self.LDAP],
            recycle_bin=[{"users": [{"id": "gone", "provider": "ldap"}]}],
            logged_users=[
                _logged_user("ldap-user"),
                _logged_user("gone", deleted=True),
            ],
            started_desktops=[
                _started_desktop("d1", "ldap-user"),
                _started_desktop("d2", "gone", deployment_id="dep"),
            ],
        )

        assert usage["users"] == {
            "total": 1,
            "by_role": {"manager": 0, "advanced": 0, "user": 1},
            "deleted": 0,
        }
        assert usage["desktops"]["total"] == 1
        assert usage["desktops"]["from_deployments"] == 0
        assert usage["deployments"]["total"] == 0

    def test_deleted_users_count_when_provider_is_omitted(self, monthly_usage):
        usage = monthly_usage(
            users=[self.LDAP],
            logged_users=[
                _logged_user("ldap-user"),
                _logged_user("gone", deleted=True),
            ],
            started_desktops=[_started_desktop("d1", "gone", deployment_id="dep")],
        )

        assert usage["users"]["total"] == 2
        assert usage["users"]["deleted"] == 1
        assert usage["desktops"]["total"] == 1
        assert usage["deployments"]["total"] == 1

    def test_provider_keeps_a_deleted_desktop_of_an_existing_user(self, monthly_usage):
        usage = monthly_usage(
            provider="ldap",
            users=[self.LDAP],
            started_desktops=[_started_desktop("d1", "ldap-user", deleted=True)],
        )

        assert usage["desktops"]["total"] == 1
        assert usage["desktops"]["deleted"] == 1

    def test_provider_keeps_a_desktop_through_its_existing_owner(self, monthly_usage):
        usage = monthly_usage(
            provider="ldap",
            users=[self.LDAP],
            started_desktops=[
                _started_desktop("d1", "gone", gpu=True),
                _started_desktop("d1", "ldap-user"),
            ],
        )

        assert usage["desktops"]["total"] == 1
        assert usage["desktops"]["gpu"] == 0

    def test_provider_ignores_rows_without_an_owner(self, monthly_usage):
        usage = monthly_usage(
            provider="ldap",
            users=[self.LDAP],
            started_desktops=[
                _started_desktop("d1", None),
                _started_desktop("d2", "ldap-user"),
            ],
        )

        assert usage["desktops"]["total"] == 1

    def test_provider_leaves_out_users_without_one(self, monthly_usage):
        usage = monthly_usage(
            provider="ldap",
            users=[self.LDAP, {"id": "no-provider"}],
            logged_users=[_logged_user("ldap-user"), _logged_user("no-provider")],
        )

        assert usage["users"]["total"] == 1

    def test_provider_matches_users_of_every_lookup_batch(
        self, monthly_usage, monkeypatch
    ):
        from isardvdi_common.lib.stats import stats as mod

        monkeypatch.setattr(mod, "_USAGE_GET_ALL_BATCH", 2)
        usage = monthly_usage(
            provider="ldap",
            users=[{"id": f"u{i}", "provider": "ldap"} for i in range(5)],
            logged_users=[_logged_user(f"u{i}") for i in range(5)],
        )

        assert usage["users"]["total"] == 5
