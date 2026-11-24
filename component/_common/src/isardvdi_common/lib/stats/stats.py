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

These endpoints are polled continuously (an admin dashboard plus the stats
collector), and every one of them aggregates over tables that reach six figures
on large installs, so a plain TTL cache is the wrong shape: the poll period is
longer than any TTL worth serving, which makes every request a blocking miss,
and concurrent misses all run the same scan. They are read through
stale-while-revalidate caches instead — a caller is served the last value
immediately and the recomputation happens on a background worker.

``get_monthly_usage`` is the exception: it reads the ``logs_users`` and
``logs_desktops`` tables, is called on demand and is not cached.

Set ``STATS_CACHE_TTL_S`` to override every TTL below (``0`` disables caching
entirely) when developing or debugging against live data.
"""

from datetime import datetime, timedelta, timezone
from itertools import batched
from os import environ

from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.stale_while_revalidate import (
    KeyedStaleWhileRevalidate,
    StaleWhileRevalidate,
    swr_cached,
    swr_cached_keyed,
)
from rethinkdb import r
from rethinkdb.ast import RqlQuery

# An entry ages from the end of its fetch: a TTL equal to the period refreshes
# only on every other poll.
_TTL_FRACTION_OF_PERIOD = 2 / 3


def _ttl(period: float) -> float:
    override = environ.get("STATS_CACHE_TTL_S")
    if override is not None:
        return float(override)
    return period * _TTL_FRACTION_OF_PERIOD


# TTL rule: the value must be as fresh as its caller's cadence allows, so the
# TTL sits just below that cadence. A longer one does not make refreshes cheaper
# in any way that matters, it only serves older data. What keeps
# parallel consumers from multiplying the work is not the TTL, it is that a stale
# value is served immediately and only ONE refresh runs however many callers
# arrive inside the interval.
#
# The two drivers, both read from this repository:
#   * the metrics collector, one call per scrape — 30 s (docker/grafana-alloy/metrics.alloy)
#   * the admin desktop-status page, read live — the operator picks the interval
#     from a selector offering 1 s to 1 minute, defaulting to 5 s
#     (webapp templates/admin/pages/desktops_status.html, desktops_status.js)
_COLLECTOR_SCRAPE_S = 30
_ADMIN_PANEL_POLL_S = 5
_ADMIN_PANEL_MIN_POLL_S = 1

# Ceiling on how old a served value may get. Below it, staleness is a nuisance;
# beyond it an operator could decide something on numbers old enough to be
# wrong, so the endpoint fails instead and the collector's own scrape failure
# becomes the signal. The first successful refresh clears it by itself.
_COLLECTOR_MAX_STALE_S = 3 * _COLLECTOR_SCRAPE_S
_PANEL_MAX_STALE_S = 120

# Live admin panel. Both sit on the same screen and share one operator-chosen
# interval, but they are not driven alike: the status summary starts polling when
# the page opens, while the per-category table only polls once its checkbox is
# ticked — off by default, and its timer is cleared when it is unticked. They do
# not get the same TTL, on purpose. The summary is the graph the operator watches
# and is the cheapest of the two queries, so it follows the fastest interval the
# selector offers. The table costs a good deal more (a pluck, two group/ungroup
# rounds and a category lookup per group), is not graphed, and is opt-in, so it
# stays at the default interval rather than being recomputed every second for as
# long as somebody leaves the page open with the box ticked.
_desktops_stats_cache = StaleWhileRevalidate(
    ttl=_ttl(_ADMIN_PANEL_MIN_POLL_S),
    name="desktops_stats",
    max_stale=_PANEL_MAX_STALE_S,
)
_domains_by_category_cache = StaleWhileRevalidate(
    ttl=_ttl(_ADMIN_PANEL_POLL_S),
    name="domains_by_category_count",
    max_stale=_PANEL_MAX_STALE_S,
)
# Collector-driven: the scrape interval itself.
_domains_status_cache = StaleWhileRevalidate(
    ttl=_ttl(_COLLECTOR_SCRAPE_S),
    name="domains_status",
    max_stale=_COLLECTOR_MAX_STALE_S,
)
_kind_cache = KeyedStaleWhileRevalidate(
    ttl=_ttl(_COLLECTOR_SCRAPE_S),
    maxsize=8,
    name="kind",
    max_stale=_COLLECTOR_MAX_STALE_S,
)
_categories_deployments_cache = StaleWhileRevalidate(
    ttl=_ttl(_COLLECTOR_SCRAPE_S),
    name="categories_deployments",
    max_stale=_COLLECTOR_MAX_STALE_S,
)
_group_by_categories_cache = StaleWhileRevalidate(
    ttl=_ttl(_COLLECTOR_SCRAPE_S),
    name="group_by_categories",
    max_stale=_COLLECTOR_MAX_STALE_S,
)
# No route reaches these two today (nothing calls the service methods in front
# of them). Cached for parity; do not read a TTL rule off them.
_users_stats_cache = StaleWhileRevalidate(
    ttl=_ttl(_COLLECTOR_SCRAPE_S), name="users_stats", max_stale=_COLLECTOR_MAX_STALE_S
)
_templates_stats_cache = StaleWhileRevalidate(
    ttl=_ttl(_COLLECTOR_SCRAPE_S),
    name="templates_stats",
    max_stale=_COLLECTOR_MAX_STALE_S,
)

# Steady-state desktop statuses surfaced by category aggregates; anything
# else is "Other" and must be surfaced for admin triage.
STABLE_STATUS = ["Started", "Stopped", "Failed"]

USAGE_ROLES = ("manager", "advanced", "user")

# RethinkDB refuses 100k groups by default, and each temporary desktop is a new id.
_USAGE_ARRAY_LIMIT = 10_000_000
_USAGE_GET_ALL_BATCH = 10_000


def _has_vgpus(value: RqlQuery) -> RqlQuery:
    """ReQL predicate: ``value`` lists at least one vGPU reservable."""
    return (
        value.default([])
        .filter(lambda vgpu: r.expr([None, "None"]).contains(vgpu).not_())
        .count()
        .gt(0)
    )


class StatsProcessed(RethinkSharedConnection):
    """System-wide statistics aggregations."""

    @classmethod
    @swr_cached(_users_stats_cache)
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
    @swr_cached(_desktops_stats_cache)
    def get_desktops_stats(cls) -> dict:
        """Return total desktops and per-status counts.

        One grouped pass over the desktop range of the ``kind_status`` index.
        The previous count plus ``group("status")`` on a non-indexed field read
        every desktop document twice, and grouping the whole table and dropping
        the template half costs nearly twice as much as restricting the range
        first — measured on 100k domains, 210 ms against 116 ms, for byte-equal
        output. Sharing the full fold with ``get_domains_status`` saves nothing
        across the two endpoints either: they sit behind separate caches with
        separate TTLs, so each refresh runs its own query.

        ``total`` is the sum of the per-status groups rather than an independent
        row count, which are the same number only while every desktop carries a
        ``status``: a document missing it is absent from the compound index.
        ``status`` is required on the domain model, and the endpoint that
        reports the per-status breakdown has always been blind to such a row
        anyway, so this keeps the two numbers from disagreeing instead of
        letting one of them quietly count more.
        """
        with cls._rdb_context():
            status = (
                r.table("domains")
                .between(
                    ["desktop", r.minval],
                    ["desktop", r.maxval],
                    index="kind_status",
                )
                .group("status")
                .count()
                .run(cls._rdb_connection)
            )
        return {"total": sum(status.values()), "status": status}

    @classmethod
    def clear_get_desktops_stats_cache(cls) -> None:
        """Invalidate the desktops-stats cache."""
        _desktops_stats_cache.clear()

    @classmethod
    @swr_cached(_templates_stats_cache)
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
    @swr_cached(_domains_status_cache)
    def get_domains_status(cls) -> dict:
        """Return per-kind, per-status domain counts."""
        return cls._domains_status_by_kind()

    @classmethod
    def _domains_status_by_kind(cls) -> dict:
        """Group on the ``kind_status`` compound index and fold the cursor
        into ``{"desktop": {<status>: <n>}, "template": {...}}``."""
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
    @swr_cached_keyed(_kind_cache, key=lambda cls, kind: kind)
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
            query = r.table(kind).pluck(
                "id", "status", "only_forced", {"degraded": ["is_degraded", "reason"]}
            )
        elif kind == "categories":
            query = r.table(kind).pluck("id", "name")
        elif kind == "groups":
            query = r.table(kind).pluck("id", "name", "parent_category")
        else:
            raise Error("bad_request", f"Unknown kind: {kind}")

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def clear_get_kind_cache(cls) -> None:
        """Invalidate every kind inventory."""
        _kind_cache.clear()

    @classmethod
    @swr_cached(_categories_deployments_cache)
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
    def clear_get_categories_deployments_cache(cls) -> None:
        """Invalidate the categories-deployments cache."""
        _categories_deployments_cache.clear()

    @classmethod
    @swr_cached(_domains_by_category_cache)
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
    def clear_get_domains_by_category_count_cache(cls) -> None:
        """Invalidate the domains-by-category cache."""
        _domains_by_category_cache.clear()

    @classmethod
    @swr_cached(_group_by_categories_cache)
    def get_group_by_categories(cls) -> dict:
        """Return per-category users + desktops + templates summary.

        Three grouped passes, folded per category:

        * users (total, enabled/disabled split, per-role counts);
        * desktops (total + ``Started``/``Stopped``/``Failed``/``Other``);
        * templates (total + enabled/disabled).
        """
        with cls._rdb_context():
            categories = list(
                r.table("categories").pluck("id")["id"].run(cls._rdb_connection)
            )
            users = (
                r.table("users")
                .group("category", "role", lambda user: user["active"].eq(True))
                .count()
                .run(cls._rdb_connection)
            )
            desktops = (
                r.table("domains")
                .between(
                    ["desktop", r.minval],
                    ["desktop", r.maxval],
                    index="kind_category",
                )
                .group("category", "status")
                .count()
                .run(cls._rdb_connection)
            )
            templates = (
                r.table("domains")
                .between(
                    ["template", r.minval],
                    ["template", r.maxval],
                    index="kind_category",
                )
                .group(
                    "category",
                    lambda template: r.branch(
                        template["enabled"].eq(True),
                        True,
                        template["enabled"].eq(False),
                        False,
                        None,
                    ),
                )
                .count()
                .run(cls._rdb_connection)
            )

        result: dict = {}
        for category in categories:
            result[category] = {
                "users": {
                    "total": 0,
                    "status": {"enabled": 0, "disabled": 0},
                    "roles": {},
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

        for (category, role, active), count in users.items():
            if category not in result:
                continue
            summary = result[category]["users"]
            summary["total"] += count
            summary["status"]["enabled" if active is True else "disabled"] += count
            # A missing role groups as ``None``, a key the response schema's
            # ``dict[str, int]`` rejects; an empty one was always dropped too.
            if role:
                summary["roles"][role] = summary["roles"].get(role, 0) + count

        for (category, status), count in desktops.items():
            if category not in result:
                continue
            summary = result[category]["desktops"]
            summary["total"] += count
            summary["status"][status if status in STABLE_STATUS else "Other"] += count

        for (category, enabled), count in templates.items():
            if category not in result:
                continue
            summary = result[category]["templates"]
            summary["total"] += count
            # A template missing ``enabled`` is in the total but in neither
            # bucket, like the ``template_enabled_category`` counts were.
            if enabled is True:
                summary["status"]["enabled"] += count
            elif enabled is False:
                summary["status"]["disabled"] += count

        return result

    @classmethod
    def clear_get_group_by_categories_cache(cls) -> None:
        """Invalidate the group-by-categories cache."""
        _group_by_categories_cache.clear()

    @classmethod
    def get_monthly_usage(
        cls,
        category: str | None = None,
        provider: str | None = None,
        month: str | None = None,
    ) -> dict:
        """Return the distinct users, desktops and deployments active in ``month``
        (``YYYY-MM``, UTC), by default the current one."""
        start, end = cls._month_range(month)
        users = cls._monthly_users(start, end, category)
        desktop_owners = cls._monthly_desktops(start, end, category)
        if provider is not None:
            owners = {row["owner_user_id"] for row in [*users, *desktop_owners]}
            matching = cls._users_with_provider(owners - {None}, provider)
            users = [row for row in users if row["owner_user_id"] in matching]
            desktop_owners = [
                row for row in desktop_owners if row["owner_user_id"] in matching
            ]

        by_role = dict.fromkeys(USAGE_ROLES, 0)
        for user in users:
            for role in user["roles"]:
                by_role[role] += 1

        by_desktop: dict[str, dict] = {}
        deployment_ids: set[str] = set()
        for row in desktop_owners:
            deployment_ids.update(row["deployment_ids"])
            desktop = by_desktop.setdefault(row["desktop_id"], row)
            desktop["gpu"] = desktop["gpu"] or row["gpu"]
            desktop["deployment_ids"] = (
                desktop["deployment_ids"] or row["deployment_ids"]
            )
        desktops = by_desktop.values()

        return {
            "period": {"start": start, "end": end},
            "users": {
                "total": len(users),
                "by_role": by_role,
                "deleted": sum(1 for user in users if user["deleted"]),
            },
            "desktops": {
                "total": len(desktops),
                "gpu": sum(1 for desktop in desktops if desktop["gpu"]),
                "servers": sum(1 for desktop in desktops if desktop["server"]),
                "from_deployments": sum(
                    1 for desktop in desktops if desktop["deployment_ids"]
                ),
                "deleted": sum(1 for desktop in desktops if desktop["deleted"]),
            },
            "deployments": cls._monthly_deployments(deployment_ids),
        }

    @staticmethod
    def _month_range(month: str | None) -> tuple[datetime, datetime]:
        from isardvdi_common.helpers.error_factory import Error

        now = datetime.now(timezone.utc)
        if month is None:
            month = now.strftime("%Y-%m")
        start = datetime.strptime(month, "%Y-%m").replace(tzinfo=timezone.utc)
        if start > now:
            raise Error("bad_request", f"Month {month} is in the future")
        next_month = (start + timedelta(days=32)).replace(day=1)
        return start, min(now, next_month)

    @classmethod
    def _users_with_provider(cls, user_ids: set[str], provider: str) -> set[str]:
        """Return the ``user_ids`` of existing users with ``provider``."""
        matching: set[str] = set()
        with cls._rdb_context():
            for batch in batched(user_ids, _USAGE_GET_ALL_BATCH):
                matching.update(
                    r.table("users")
                    .get_all(r.args(batch))
                    .filter({"provider": provider})["id"]
                    .run(cls._rdb_connection)
                )
        return matching

    @classmethod
    def _monthly_users(
        cls, start: datetime, end: datetime, category: str | None
    ) -> list[dict]:
        query = r.table("logs_users").between(start, end, index="started_time")
        if category is not None:
            query = query.filter({"owner_category_id": category})
        with cls._rdb_context():
            return list(
                query.filter(
                    lambda log: r.expr(USAGE_ROLES).contains(log["owner_role_id"])
                )
                .group("owner_user_id")["owner_role_id"]
                .distinct()
                .ungroup()
                .map(
                    lambda group: {
                        "owner_user_id": group["group"],
                        "roles": group["reduction"],
                        "deleted": r.table("users").get(group["group"]).eq(None),
                    }
                )
                .run(cls._rdb_connection, array_limit=_USAGE_ARRAY_LIMIT)
            )

    @classmethod
    def _monthly_desktops(
        cls, start: datetime, end: datetime, category: str | None
    ) -> list[dict]:
        """Return one row per desktop and owner."""
        query = r.table("logs_desktops").between(start, end, index="starting_time")
        if category is not None:
            query = query.filter({"owner_category_id": category})
        with cls._rdb_context():
            return list(
                query.group("desktop_id", "owner_user_id")
                .map(
                    lambda log: {
                        "gpu": _has_vgpus(log["hardware_bookables_vgpus"]),
                        "deployment_ids": r.branch(
                            log["deployment_id"].default(None).eq(None),
                            [],
                            [log["deployment_id"]],
                        ),
                    }
                )
                .reduce(
                    lambda a, b: {
                        "gpu": a["gpu"].or_(b["gpu"]),
                        "deployment_ids": a["deployment_ids"].set_union(
                            b["deployment_ids"]
                        ),
                    }
                )
                .ungroup()
                .map(
                    lambda group: r.table("domains")
                    .get(group["group"][0])
                    .do(
                        lambda domain: group["reduction"].merge(
                            {
                                "desktop_id": group["group"][0],
                                "owner_user_id": group["group"][1],
                                "deleted": domain.eq(None),
                                "server": domain["server"].default(False).eq(True),
                            }
                        )
                    )
                )
                .run(cls._rdb_connection, array_limit=_USAGE_ARRAY_LIMIT)
            )

    @classmethod
    def _monthly_deployments(cls, deployment_ids: set[str]) -> dict:
        if not deployment_ids:
            return {"total": 0, "gpu": 0, "deleted": 0}
        with cls._rdb_context():
            deployments = list(
                r.expr(sorted(deployment_ids))
                .map(
                    lambda deployment_id: r.table("deployments")
                    .get(deployment_id)
                    .do(
                        lambda deployment: {
                            "deleted": deployment.eq(None),
                            "gpu": deployment["create_dict"]
                            .default([])
                            .contains(
                                lambda desktop: _has_vgpus(
                                    desktop["reservables"]["vgpus"]
                                )
                            ),
                        }
                    )
                )
                .run(cls._rdb_connection, array_limit=_USAGE_ARRAY_LIMIT)
            )
        return {
            "total": len(deployments),
            "gpu": sum(1 for deployment in deployments if deployment["gpu"]),
            "deleted": sum(1 for deployment in deployments if deployment["deleted"]),
        }
