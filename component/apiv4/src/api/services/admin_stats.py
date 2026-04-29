#
#   Copyright © 2025 IsardVDI
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from cachetools import TTLCache, cached
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.error_factory import Error
from rethinkdb import r

STABLE_STATUS = ["Started", "Stopped", "Failed"]

_users_cache = TTLCache(maxsize=1, ttl=10)
_desktops_cache = TTLCache(maxsize=1, ttl=5)
_templates_cache = TTLCache(maxsize=1, ttl=10)
_domains_status_cache = TTLCache(maxsize=1, ttl=5)


class AdminStatsService:
    """Service for system statistics."""

    @staticmethod
    @cached(cache=_users_cache)
    def get_users_stats():
        with RethinkSharedConnection._rdb_context():
            users_count = (
                r.table("users").count().run(RethinkSharedConnection._rdb_connection)
            )
        with RethinkSharedConnection._rdb_context():
            users_active = (
                r.table("users")
                .get_all(True, index="active")
                .count()
                .run(RethinkSharedConnection._rdb_connection)
            )
        with RethinkSharedConnection._rdb_context():
            roles = (
                r.table("users")
                .group("role")
                .count()
                .run(RethinkSharedConnection._rdb_connection)
            )
        return {
            "total": users_count,
            "status": {
                "enabled": users_active,
                "disabled": users_count - users_active,
            },
            "roles": roles,
        }

    @staticmethod
    @cached(cache=_desktops_cache)
    def get_desktops_stats():
        with RethinkSharedConnection._rdb_context():
            total = (
                r.table("domains")
                .get_all("desktop", index="kind")
                .count()
                .run(RethinkSharedConnection._rdb_connection)
            )
        with RethinkSharedConnection._rdb_context():
            group_by_status = (
                r.table("domains")
                .get_all("desktop", index="kind")
                .group("status")
                .count()
                .run(RethinkSharedConnection._rdb_connection)
            )
        return {
            "total": total,
            "status": group_by_status,
        }

    @staticmethod
    @cached(cache=_templates_cache)
    def get_templates_stats():
        with RethinkSharedConnection._rdb_context():
            templates = list(
                r.table("domains")
                .get_all("template", index="kind")
                .pluck("enabled")
                .run(RethinkSharedConnection._rdb_connection)
            )
        # Older template docs predate the ``enabled`` field; treat missing
        # as disabled rather than crashing the whole stats endpoint.
        templates_enabled = len([t for t in templates if t.get("enabled")])
        return {
            "total": len(templates),
            "enabled": templates_enabled,
            "disabled": len(templates) - templates_enabled,
        }

    @staticmethod
    def get_general_stats():
        return {
            "users": AdminStatsService.get_users_stats(),
            "desktops": AdminStatsService.get_desktops_stats(),
            "templates": AdminStatsService.get_templates_stats(),
        }

    @staticmethod
    @cached(cache=_domains_status_cache)
    def get_domains_status():
        with RethinkSharedConnection._rdb_context():
            domains = (
                r.table("domains")
                .group(index="kind_status")
                .count()
                .run(RethinkSharedConnection._rdb_connection)
            )
        d = {"desktop": {}, "template": {}, "server": {}}
        for k, v in domains.items():
            kind = k[0]
            if kind not in d:
                d[kind] = {}
            d[kind][k[1]] = v
        return d

    @staticmethod
    def get_kind(kind):
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

        with RethinkSharedConnection._rdb_context():
            return list(query.run(RethinkSharedConnection._rdb_connection))

    @staticmethod
    def get_category_status():
        with RethinkSharedConnection._rdb_context():
            desktops = (
                r.table("domains")
                .get_all("desktop", index="kind")
                .pluck("category", "status", "kind")
                .group("category", "status")
                .count()
                .run(RethinkSharedConnection._rdb_connection)
            )
        with RethinkSharedConnection._rdb_context():
            templates = (
                r.table("domains")
                .get_all("template", index="kind")
                .pluck("category", "status", "kind")
                .group("category", "status")
                .count()
                .run(RethinkSharedConnection._rdb_connection)
            )
        result = {}
        for key, value in desktops.items():
            if key[1] in STABLE_STATUS:
                continue
            if key[0] not in result.keys():
                result[key[0]] = {"desktops_wrong_status": {key[1]: value}}
            else:
                result[key[0]] = {
                    **result[key[0]],
                    **{"desktops_wrong_status": {key[1]: value}},
                }
        for key, value in templates.items():
            if key[1] == "Stopped":
                continue
            if key[0] not in result.keys():
                result[key[0]] = {"templates_wrong_status": {key[1]: value}}
            else:
                result[key[0]] = {
                    **result[key[0]],
                    **{"templates_wrong_status": {key[1]: value}},
                }
        return result

    @staticmethod
    def get_group_by_categories():
        with RethinkSharedConnection._rdb_context():
            categories = list(
                r.table("categories")
                .pluck("id")["id"]
                .run(RethinkSharedConnection._rdb_connection)
            )

        result = {}
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

        with RethinkSharedConnection._rdb_context():
            for category in categories:
                result[category]["users"]["total"] = (
                    r.table("users")
                    .get_all(category, index="category")
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )
                result[category]["users"]["status"]["enabled"] = (
                    r.table("users")
                    .get_all(category, index="category")
                    .filter({"active": True})
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
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
                    .run(RethinkSharedConnection._rdb_connection)
                )

        with RethinkSharedConnection._rdb_context():
            for category in categories:
                result[category]["desktops"]["total"] = (
                    r.table("domains")
                    .get_all(["desktop", category], index="kind_category")
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )
                for status in STABLE_STATUS:
                    result[category]["desktops"]["status"][status] = (
                        r.table("domains")
                        .get_all(
                            ["desktop", status, category],
                            index="kind_status_category",
                        )
                        .count()
                        .run(RethinkSharedConnection._rdb_connection)
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
                    .run(RethinkSharedConnection._rdb_connection)
                )

        with RethinkSharedConnection._rdb_context():
            for category in categories:
                result[category]["templates"]["total"] = (
                    r.table("domains")
                    .get_all(["template", category], index="kind_category")
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )
                result[category]["templates"]["status"]["enabled"] = (
                    r.table("domains")
                    .get_all(
                        ["template", True, category],
                        index="template_enabled_category",
                    )
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )
                result[category]["templates"]["status"]["disabled"] = (
                    r.table("domains")
                    .get_all(
                        ["template", False, category],
                        index="template_enabled_category",
                    )
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )

        return result

    @staticmethod
    def get_categories_kind_state(kind, state=False):
        query = {}
        with RethinkSharedConnection._rdb_context():
            categories = list(
                r.table("categories")
                .pluck("id")["id"]
                .run(RethinkSharedConnection._rdb_connection)
            )

        if kind == "desktop":
            for category in categories:
                if state and state != "false":
                    query[category] = {"desktops": {"status": {state: ""}}}
                    with RethinkSharedConnection._rdb_context():
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
                                .run(RethinkSharedConnection._rdb_connection)
                            )
                        else:
                            query[category]["desktops"]["status"][state] = (
                                r.table("domains")
                                .get_all(
                                    ["desktop", state, category],
                                    index="kind_status_category",
                                )
                                .count()
                                .run(RethinkSharedConnection._rdb_connection)
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
                    with RethinkSharedConnection._rdb_context():
                        query[category]["desktops"]["total"] = (
                            r.table("domains")
                            .get_all(
                                ["desktop", category],
                                index="kind_category",
                            )
                            .count()
                            .run(RethinkSharedConnection._rdb_connection)
                        )
                        for ds in STABLE_STATUS:
                            query[category]["desktops"]["status"][ds] = (
                                r.table("domains")
                                .get_all(
                                    ["desktop", ds, category],
                                    index="kind_status_category",
                                )
                                .count()
                                .run(RethinkSharedConnection._rdb_connection)
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
                            .run(RethinkSharedConnection._rdb_connection)
                        )
                    return query

        elif kind == "template":
            for category in categories:
                if state == "enabled":
                    query[category] = {"templates": {"status": {"enabled": ""}}}
                    with RethinkSharedConnection._rdb_context():
                        query[category]["templates"]["status"]["enabled"] = (
                            r.table("domains")
                            .get_all(
                                ["template", True, category],
                                index="template_enabled_category",
                            )
                            .count()
                            .run(RethinkSharedConnection._rdb_connection)
                        )
                    return query
                elif state == "disabled":
                    query[category] = {"templates": {"status": {"disabled": ""}}}
                    with RethinkSharedConnection._rdb_context():
                        query[category]["templates"]["status"]["disabled"] = (
                            r.table("domains")
                            .get_all(
                                ["template", False, category],
                                index="template_enabled_category",
                            )
                            .count()
                            .run(RethinkSharedConnection._rdb_connection)
                        )
                    return query
                else:
                    query[category] = {
                        "templates": {
                            "total": "",
                            "status": {"enabled": "", "disabled": ""},
                        }
                    }
                    with RethinkSharedConnection._rdb_context():
                        query[category]["templates"]["total"] = (
                            r.table("domains")
                            .get_all(
                                ["template", category],
                                index="kind_category",
                            )
                            .count()
                            .run(RethinkSharedConnection._rdb_connection)
                        )
                        query[category]["templates"]["status"]["enabled"] = (
                            r.table("domains")
                            .get_all(
                                ["template", True, category],
                                index="template_enabled_category",
                            )
                            .count()
                            .run(RethinkSharedConnection._rdb_connection)
                        )
                        query[category]["templates"]["status"]["disabled"] = (
                            r.table("domains")
                            .get_all(
                                ["template", False, category],
                                index="template_enabled_category",
                            )
                            .count()
                            .run(RethinkSharedConnection._rdb_connection)
                        )
                    return query
        return query

    @staticmethod
    def get_categories_limits_hardware():
        with RethinkSharedConnection._rdb_context():
            categories = list(
                r.table("categories")
                .pluck("id", "limits")
                .run(RethinkSharedConnection._rdb_connection)
            )

        query = {}
        for category in categories:
            query[category["id"]] = {
                "Started desktops": "",
                "vCPUs": {"Limit": "", "Running": ""},
                "Memory": {"Limit": "", "Running": ""},
            }
            with RethinkSharedConnection._rdb_context():
                query[category["id"]]["Started desktops"] = (
                    r.table("domains")
                    .get_all(
                        ["desktop", "Started", category["id"]],
                        index="kind_status_category",
                    )
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )

            if category["limits"] is False:
                query[category["id"]]["vCPUs"]["Limit"] = 0
                query[category["id"]]["Memory"]["Limit"] = 0
            else:
                query[category["id"]]["vCPUs"]["Limit"] = category["limits"]["vcpus"]
                query[category["id"]]["Memory"]["Limit"] = category["limits"]["memory"]

            with RethinkSharedConnection._rdb_context():
                query[category["id"]]["vCPUs"]["Running"] = (
                    r.table("domains")
                    .get_all(
                        ["desktop", "Started", category["id"]],
                        index="kind_status_category",
                    )["create_dict"]["hardware"]["vcpus"]
                    .sum()
                    .run(RethinkSharedConnection._rdb_connection)
                )
            with RethinkSharedConnection._rdb_context():
                query[category["id"]]["Memory"]["Running"] = (
                    r.table("domains")
                    .get_all(
                        ["desktop", "Started", category["id"]],
                        index="kind_status_category",
                    )["create_dict"]["hardware"]["memory"]
                    .sum()
                    .run(RethinkSharedConnection._rdb_connection)
                )
        return query

    @staticmethod
    def get_categories_deployments():
        with RethinkSharedConnection._rdb_context():
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
                .run(RethinkSharedConnection._rdb_connection)
            )

    @staticmethod
    def get_domains_by_category_count():
        with RethinkSharedConnection._rdb_context():
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
                .run(RethinkSharedConnection._rdb_connection)
            )
