#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Layer-2 helpers for system-wide admin statistics.

Backs the ``/api/v4/admin/stats*`` endpoints with table-level
aggregations over ``users``, ``domains`` (kind=desktop/template),
``categories`` and ``deployments``. Cached entry points keep the admin
dashboard cheap to refresh; every cache is module-level + carries a
``clear_*`` invalidator (B8 contract).
"""

from cachetools import TTLCache, cached
from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from rethinkdb import r

_users_stats_cache: TTLCache = TTLCache(maxsize=1, ttl=10)
_desktops_stats_cache: TTLCache = TTLCache(maxsize=1, ttl=5)
_templates_stats_cache: TTLCache = TTLCache(maxsize=1, ttl=10)
_domains_status_cache: TTLCache = TTLCache(maxsize=1, ttl=5)

# Steady-state desktop statuses surfaced by category aggregates; anything
# else is "Other" and must be surfaced for admin triage.
STABLE_STATUS = ["Started", "Stopped", "Failed"]


class StatsProcessed(RethinkSharedConnection):
    """System-wide statistics aggregations."""

    @classmethod
    @cached(cache=_users_stats_cache)
    def get_users_stats(cls) -> dict:
        """Return total users, enabled/disabled split, and per-role counts."""
        with cls._rdb_context():
            users_count = r.table("users").count().run(cls._rdb_connection)
        with cls._rdb_context():
            users_active = (
                r.table("users")
                .get_all(True, index="active")
                .count()
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            roles = r.table("users").group("role").count().run(cls._rdb_connection)
        return {
            "total": users_count,
            "status": {
                "enabled": users_active,
                "disabled": users_count - users_active,
            },
            "roles": roles,
        }

    @classmethod
    def clear_get_users_stats_cache(cls) -> None:
        """Invalidate the users-stats cache."""
        _users_stats_cache.clear()

    @classmethod
    @cached(cache=_desktops_stats_cache)
    def get_desktops_stats(cls) -> dict:
        """Return total desktops and per-status counts."""
        with cls._rdb_context():
            total = (
                r.table("domains")
                .get_all("desktop", index="kind")
                .count()
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            group_by_status = (
                r.table("domains")
                .get_all("desktop", index="kind")
                .group("status")
                .count()
                .run(cls._rdb_connection)
            )
        return {"total": total, "status": group_by_status}

    @classmethod
    def clear_get_desktops_stats_cache(cls) -> None:
        """Invalidate the desktops-stats cache."""
        _desktops_stats_cache.clear()

    @classmethod
    @cached(cache=_templates_stats_cache)
    def get_templates_stats(cls) -> dict:
        """Return total templates and enabled/disabled split.

        Older template docs predate the ``enabled`` field; treat missing
        as disabled rather than crashing the whole stats endpoint.
        """
        with cls._rdb_context():
            templates = list(
                r.table("domains")
                .get_all("template", index="kind")
                .pluck("enabled")
                .run(cls._rdb_connection)
            )
        templates_enabled = len([t for t in templates if t.get("enabled")])
        return {
            "total": len(templates),
            "enabled": templates_enabled,
            "disabled": len(templates) - templates_enabled,
        }

    @classmethod
    def clear_get_templates_stats_cache(cls) -> None:
        """Invalidate the templates-stats cache."""
        _templates_stats_cache.clear()

    @classmethod
    def get_general_stats(cls) -> dict:
        """Return combined users + desktops + templates summary."""
        return {
            "users": cls.get_users_stats(),
            "desktops": cls.get_desktops_stats(),
            "templates": cls.get_templates_stats(),
        }

    @classmethod
    @cached(cache=_domains_status_cache)
    def get_domains_status(cls) -> dict:
        """Return per-kind, per-status domain counts.

        Groups on the ``kind_status`` compound index and folds the
        cursor into ``{"desktop": {<status>: <n>}, "template": {...}}``.
        """
        with cls._rdb_context():
            domains = (
                r.table("domains")
                .group(index="kind_status")
                .count()
                .run(cls._rdb_connection)
            )
        result: dict = {"desktop": {}, "template": {}}
        for k, v in domains.items():
            kind = k[0]
            if kind not in result:
                result[kind] = {}
            result[kind][k[1]] = v
        return result

    @classmethod
    def clear_get_domains_status_cache(cls) -> None:
        """Invalidate the domains-status cache."""
        _domains_status_cache.clear()

    @classmethod
    def get_kind(cls, kind: str) -> list[dict]:
        """Return an inventory of rows for ``kind``.

        Recognised kinds: ``desktops``, ``templates``, ``users``,
        ``hypervisors``, ``categories``, ``groups``. Each branch
        plucks just the fields the admin dashboard renders. Anything
        else raises ``bad_request``.
        """
        from isardvdi_common.helpers.error_factory import Error

        if kind == "desktops":
            query = (
                r.table("domains").get_all("desktop", index="kind").pluck("id", "user")
            )
        elif kind == "templates":
            query = r.table("domains").get_all("template", index="kind").pluck("id")
        elif kind == "users":
            query = r.table(kind).pluck("id", "role", "category", "group")
        elif kind == "hypervisors":
            query = r.table(kind).pluck("id", "status", "only_forced")
        elif kind == "categories":
            query = r.table(kind).pluck("id", "name")
        elif kind == "groups":
            query = r.table(kind).pluck("id", "name", "parent_category")
        else:
            raise Error("bad_request", f"Unknown kind: {kind}")

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def get_category_status(cls) -> dict:
        """Return per-category wrong-status desktops + templates.

        Skips entries whose status is in ``STABLE_STATUS`` for desktops
        and ``Stopped`` for templates, since those are the expected
        steady states; everything else is something the admin should
        triage.
        """
        with cls._rdb_context():
            desktops = (
                r.table("domains")
                .get_all("desktop", index="kind")
                .pluck("category", "status", "kind")
                .group("category", "status")
                .count()
                .run(cls._rdb_connection)
            )
        with cls._rdb_context():
            templates = (
                r.table("domains")
                .get_all("template", index="kind")
                .pluck("category", "status", "kind")
                .group("category", "status")
                .count()
                .run(cls._rdb_connection)
            )
        result: dict = {}
        for key, value in desktops.items():
            if key[1] in STABLE_STATUS:
                continue
            if key[0] not in result:
                result[key[0]] = {"desktops_wrong_status": {key[1]: value}}
            else:
                result[key[0]] = {
                    **result[key[0]],
                    **{"desktops_wrong_status": {key[1]: value}},
                }
        for key, value in templates.items():
            if key[1] == "Stopped":
                continue
            if key[0] not in result:
                result[key[0]] = {"templates_wrong_status": {key[1]: value}}
            else:
                result[key[0]] = {
                    **result[key[0]],
                    **{"templates_wrong_status": {key[1]: value}},
                }
        return result

    @classmethod
    def get_categories_deployments(cls) -> dict:
        """Return deployment counts grouped by user category."""
        with cls._rdb_context():
            return (
                r.table("deployments")
                .merge(
                    lambda dom: {
                        "category": r.table("users")
                        .get(dom["user"])["category"]
                        .default("None"),
                    }
                )
                .group(r.row["category"])
                .count()
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_domains_by_category_count(cls) -> list[dict]:
        """Return per-category desktop counts grouped by status.

        Each row is ``{category, category_name, desktops: {<status>: <n>}}``.
        Backs the ``/admin/domains/started-count`` endpoint.
        """
        with cls._rdb_context():
            return list(
                r.table("domains")
                .get_all("desktop", index="kind")
                .pluck("category", "status")
                .group("category", "status")
                .count()
                .ungroup()
                .map(
                    lambda doc: {
                        "category": doc["group"][0],
                        "status": doc["group"][1],
                        "count": doc["reduction"],
                    }
                )
                .group("category")
                .ungroup()
                .map(
                    lambda doc: {
                        "category": doc["group"],
                        "category_name": r.table("categories").get(doc["group"])[
                            "name"
                        ],
                        "desktops": doc["reduction"].without("category"),
                    }
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_group_by_categories(cls) -> dict:
        """Return per-category users + desktops + templates summary.

        Iterates every category and runs three sub-aggregations:

        * users (total, enabled/disabled split, per-role counts);
        * desktops (total + ``Started``/``Stopped``/``Failed``/``Other``);
        * templates (total + enabled/disabled).

        Wraps each per-category block in a single ``_rdb_context`` so the
        connection is reused across the inner loop's queries.
        """
        with cls._rdb_context():
            categories = list(
                r.table("categories").pluck("id")["id"].run(cls._rdb_connection)
            )

        result: dict = {}
        for category in categories:
            result[category] = {
                "users": {
                    "total": 0,
                    "status": {"enabled": 0, "disabled": 0},
                    "roles": {
                        "admin": 0,
                        "manager": 0,
                        "advanced": 0,
                        "user": 0,
                    },
                },
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
                "templates": {
                    "total": 0,
                    "status": {"enabled": 0, "disabled": 0},
                },
            }

        with cls._rdb_context():
            for category in categories:
                result[category]["users"]["total"] = (
                    r.table("users")
                    .get_all(category, index="category")
                    .count()
                    .run(cls._rdb_connection)
                )
                result[category]["users"]["status"]["enabled"] = (
                    r.table("users")
                    .get_all(category, index="category")
                    .filter({"active": True})
                    .count()
                    .run(cls._rdb_connection)
                )
                result[category]["users"]["status"]["disabled"] = (
                    result[category]["users"]["total"]
                    - result[category]["users"]["status"]["enabled"]
                )
                result[category]["users"]["roles"] = (
                    r.table("users")
                    .get_all(category, index="category")
                    .group("role")
                    .count()
                    .run(cls._rdb_connection)
                )

        with cls._rdb_context():
            for category in categories:
                result[category]["desktops"]["total"] = (
                    r.table("domains")
                    .get_all(["desktop", category], index="kind_category")
                    .count()
                    .run(cls._rdb_connection)
                )
                for status in STABLE_STATUS:
                    result[category]["desktops"]["status"][status] = (
                        r.table("domains")
                        .get_all(
                            ["desktop", status, category],
                            index="kind_status_category",
                        )
                        .count()
                        .run(cls._rdb_connection)
                    )
                result[category]["desktops"]["status"]["Other"] = (
                    r.table("domains")
                    .get_all(["desktop", category], index="kind_category")
                    .filter(
                        lambda desktop: r.not_(
                            r.expr(STABLE_STATUS).contains(desktop["status"])
                        )
                    )
                    .count()
                    .run(cls._rdb_connection)
                )

        with cls._rdb_context():
            for category in categories:
                result[category]["templates"]["total"] = (
                    r.table("domains")
                    .get_all(["template", category], index="kind_category")
                    .count()
                    .run(cls._rdb_connection)
                )
                result[category]["templates"]["status"]["enabled"] = (
                    r.table("domains")
                    .get_all(
                        ["template", True, category],
                        index="template_enabled_category",
                    )
                    .count()
                    .run(cls._rdb_connection)
                )
                result[category]["templates"]["status"]["disabled"] = (
                    r.table("domains")
                    .get_all(
                        ["template", False, category],
                        index="template_enabled_category",
                    )
                    .count()
                    .run(cls._rdb_connection)
                )

        return result

    @classmethod
    def get_categories_kind_state(cls, kind: str, state: str | bool = False) -> dict:
        """Return per-category counts for a single kind/state cell.

        ``kind`` is ``desktop`` or ``template``. When ``state`` is falsy
        (``False`` / ``"false"``), returns the full breakdown the
        ``/stats/categories/{kind}`` endpoint expects; otherwise returns
        just the requested status cell. Mirrors the original apiv4
        dispatcher exactly (including the early ``return`` inside the
        loop body, which means callers only get the first category — the
        legacy contract).
        """
        query: dict = {}
        with cls._rdb_context():
            categories = list(
                r.table("categories").pluck("id")["id"].run(cls._rdb_connection)
            )

        if kind == "desktop":
            for category in categories:
                if state and state != "false":
                    query[category] = {"desktops": {"status": {state: ""}}}
                    with cls._rdb_context():
                        if state == "Other":
                            query[category]["desktops"]["status"]["Other"] = (
                                r.table("domains")
                                .get_all(
                                    ["desktop", category],
                                    index="kind_category",
                                )
                                .filter(
                                    lambda desktop: r.not_(
                                        r.expr(STABLE_STATUS).contains(
                                            desktop["status"]
                                        )
                                    )
                                )
                                .count()
                                .run(cls._rdb_connection)
                            )
                        else:
                            query[category]["desktops"]["status"][state] = (
                                r.table("domains")
                                .get_all(
                                    ["desktop", state, category],
                                    index="kind_status_category",
                                )
                                .count()
                                .run(cls._rdb_connection)
                            )
                    return query
                else:
                    query[category] = {
                        "desktops": {
                            "total": "",
                            "status": {
                                "Started": "",
                                "Stopped": "",
                                "Failed": "",
                                "Unknown": "",
                                "Other": "",
                            },
                        }
                    }
                    with cls._rdb_context():
                        query[category]["desktops"]["total"] = (
                            r.table("domains")
                            .get_all(
                                ["desktop", category],
                                index="kind_category",
                            )
                            .count()
                            .run(cls._rdb_connection)
                        )
                        for ds in STABLE_STATUS:
                            query[category]["desktops"]["status"][ds] = (
                                r.table("domains")
                                .get_all(
                                    ["desktop", ds, category],
                                    index="kind_status_category",
                                )
                                .count()
                                .run(cls._rdb_connection)
                            )
                        query[category]["desktops"]["status"]["Other"] = (
                            r.table("domains")
                            .get_all(
                                ["desktop", category],
                                index="kind_category",
                            )
                            .filter(
                                lambda desktop: r.not_(
                                    r.expr(STABLE_STATUS).contains(desktop["status"])
                                )
                            )
                            .count()
                            .run(cls._rdb_connection)
                        )
                    return query

        elif kind == "template":
            for category in categories:
                if state == "enabled":
                    query[category] = {"templates": {"status": {"enabled": ""}}}
                    with cls._rdb_context():
                        query[category]["templates"]["status"]["enabled"] = (
                            r.table("domains")
                            .get_all(
                                ["template", True, category],
                                index="template_enabled_category",
                            )
                            .count()
                            .run(cls._rdb_connection)
                        )
                    return query
                elif state == "disabled":
                    query[category] = {"templates": {"status": {"disabled": ""}}}
                    with cls._rdb_context():
                        query[category]["templates"]["status"]["disabled"] = (
                            r.table("domains")
                            .get_all(
                                ["template", False, category],
                                index="template_enabled_category",
                            )
                            .count()
                            .run(cls._rdb_connection)
                        )
                    return query
                else:
                    query[category] = {
                        "templates": {
                            "total": "",
                            "status": {"enabled": "", "disabled": ""},
                        }
                    }
                    with cls._rdb_context():
                        query[category]["templates"]["total"] = (
                            r.table("domains")
                            .get_all(
                                ["template", category],
                                index="kind_category",
                            )
                            .count()
                            .run(cls._rdb_connection)
                        )
                        query[category]["templates"]["status"]["enabled"] = (
                            r.table("domains")
                            .get_all(
                                ["template", True, category],
                                index="template_enabled_category",
                            )
                            .count()
                            .run(cls._rdb_connection)
                        )
                        query[category]["templates"]["status"]["disabled"] = (
                            r.table("domains")
                            .get_all(
                                ["template", False, category],
                                index="template_enabled_category",
                            )
                            .count()
                            .run(cls._rdb_connection)
                        )
                    return query
        return query

    @classmethod
    def get_categories_limits_hardware(cls) -> dict:
        """Return per-category hardware limits + Started-desktop usage.

        For each category, sums vCPUs and memory across started desktops
        and reports the configured ``limits.vcpus`` / ``limits.memory``
        (falling back to ``0`` when the category has ``limits = False``).
        """
        with cls._rdb_context():
            categories = list(
                r.table("categories").pluck("id", "limits").run(cls._rdb_connection)
            )

        query: dict = {}
        for category in categories:
            query[category["id"]] = {
                "Started desktops": "",
                "vCPUs": {"Limit": "", "Running": ""},
                "Memory": {"Limit": "", "Running": ""},
            }
            with cls._rdb_context():
                query[category["id"]]["Started desktops"] = (
                    r.table("domains")
                    .get_all(
                        ["desktop", "Started", category["id"]],
                        index="kind_status_category",
                    )
                    .count()
                    .run(cls._rdb_connection)
                )

            if category["limits"] is False:
                query[category["id"]]["vCPUs"]["Limit"] = 0
                query[category["id"]]["Memory"]["Limit"] = 0
            else:
                query[category["id"]]["vCPUs"]["Limit"] = category["limits"]["vcpus"]
                query[category["id"]]["Memory"]["Limit"] = category["limits"]["memory"]

            with cls._rdb_context():
                query[category["id"]]["vCPUs"]["Running"] = (
                    r.table("domains")
                    .get_all(
                        ["desktop", "Started", category["id"]],
                        index="kind_status_category",
                    )["create_dict"]["hardware"]["vcpus"]
                    .sum()
                    .run(cls._rdb_connection)
                )
            with cls._rdb_context():
                query[category["id"]]["Memory"]["Running"] = (
                    r.table("domains")
                    .get_all(
                        ["desktop", "Started", category["id"]],
                        index="kind_status_category",
                    )["create_dict"]["hardware"]["memory"]
                    .sum()
                    .run(cls._rdb_connection)
                )
        return query
