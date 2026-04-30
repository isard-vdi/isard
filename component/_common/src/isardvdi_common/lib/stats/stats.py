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
        stable_status = ["Started", "Stopped", "Failed"]
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
            if key[1] in stable_status:
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
