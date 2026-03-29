from rethinkdb import RethinkDB

r = RethinkDB()

from api import app

from ..libv2.flask_rethink import RDB
from .stale_while_revalidate import KeyedStaleWhileRevalidate, StaleWhileRevalidate

db = RDB(app)
db.init_app(app)

stable_status = ["Started", "Stopped", "Failed"]


# Cache instances for each endpoint
_users_cache = StaleWhileRevalidate(ttl=5)
_desktops_cache = StaleWhileRevalidate(ttl=10)
_domains_status_cache = StaleWhileRevalidate(ttl=5)
_templates_cache = StaleWhileRevalidate(ttl=5)
_other_status_cache = StaleWhileRevalidate(ttl=5)
_kind_cache = KeyedStaleWhileRevalidate(ttl=5, maxsize=5)
_group_by_categories_cache = StaleWhileRevalidate(ttl=60)
_categories_kind_state_cache = KeyedStaleWhileRevalidate(ttl=30, maxsize=10)
_categories_limits_hardware_cache = StaleWhileRevalidate(ttl=60)
_categories_deploys_cache = StaleWhileRevalidate(ttl=30)
_domains_by_category_count_cache = StaleWhileRevalidate(ttl=30)


def Users():
    def fetch():
        with app.app_context():
            users_count = r.table("users").count().run(db.conn)
        with app.app_context():
            users_active = (
                r.table("users").get_all(True, index="active").count().run(db.conn)
            )
        with app.app_context():
            roles = r.table("users").group("role").count().run(db.conn)
        return {
            "total": users_count,
            "status": {
                "enabled": users_active,
                "disabled": users_count - users_active,
            },
            "roles": roles,
        }

    return _users_cache.get(fetch)


def Desktops():
    # Used by webapp desktops status
    def fetch():
        with app.app_context():
            group_by_status = (
                r.table("domains")
                .get_all("desktop", index="kind")
                .group("status")
                .count()
                .run(db.conn)
            )
        return {
            "total": sum(group_by_status.values()),
            "status": group_by_status,
        }

    return _desktops_cache.get(fetch)


def DomainsStatus():
    # Used by stats go
    def fetch():
        with app.app_context():
            domains = r.table("domains").group(index="kind_status").count().run(db.conn)
        d = {}
        for k, v in domains.items():
            if k[0] not in d:
                d[k[0]] = {}
            d[k[0]][k[1]] = v
        return d

    return _domains_status_cache.get(fetch)


def Templates():
    def fetch():
        with app.app_context():
            templates = list(
                r.table("domains")
                .get_all("template", index="kind")
                .pluck("enabled")
                .run(db.conn)
            )
        templates_enabled = len([t for t in templates if t["enabled"]])
        return {
            "total": len(templates),
            "enabled": templates_enabled,
            "disabled": len(templates) - templates_enabled,
        }

    return _templates_cache.get(fetch)


def OtherStatus():
    def fetch():
        with app.app_context():
            desktops = (
                r.table("domains")
                .get_all("desktop", index="kind")
                .pluck("category", "status", "kind")
                .group("category", "status")
                .count()
                .run(db.conn)
            )
        with app.app_context():
            templates = (
                r.table("domains")
                .get_all("template", index="kind")
                .pluck("category", "status", "kind")
                .group("category", "status")
                .count()
                .run(db.conn)
            )
        result = {}
        for key, value in desktops.items():
            if key[1] in stable_status:
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

    return _other_status_cache.get(fetch)


def Kind(kind):
    def fetch():
        query = {}
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

        with app.app_context():
            return list(query.run(db.conn))

    return _kind_cache.get(kind, fetch)


def GroupByCategories():
    # Used by stats go
    # Uses indexed queries for fast O(log n) lookups per category
    def fetch():
        result = {}

        # Open a single app context for all operations
        with app.app_context():
            # Get all categories in one query
            categories = list(r.table("categories").pluck("id")["id"].run(db.conn))

            # Initialize the result structure for all categories at once
            for category in categories:
                result[category] = {
                    "users": {
                        "total": "",
                        "status": {"enabled": "", "disabled": ""},
                        "roles": {
                            "admin": "",
                            "manager": "",
                            "advanced": "",
                            "user": "",
                        },
                    },
                    "desktops": {
                        "total": "",
                        "status": {
                            "Started": "",
                            "Stopped": "",
                            "Failed": "",
                            "Other": "",
                        },
                    },
                    "templates": {
                        "total": "",
                        "status": {"enabled": "", "disabled": ""},
                    },
                }

            # Process all user-related data
            for category in categories:
                result[category]["users"]["total"] = (
                    r.table("users")
                    .get_all(category, index="category")
                    .count()
                    .run(db.conn)
                )

                result[category]["users"]["status"]["enabled"] = (
                    r.table("users")
                    .get_all(category, index="category")
                    .filter({"active": True})
                    .count()
                    .run(db.conn)
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
                    .run(db.conn)
                )

            # Process all desktop-related data
            for category in categories:
                result[category]["desktops"]["total"] = (
                    r.table("domains")
                    .get_all(["desktop", category], index="kind_category")
                    .count()
                    .run(db.conn)
                )

                for status in stable_status:
                    result[category]["desktops"]["status"][status] = (
                        r.table("domains")
                        .get_all(
                            ["desktop", status, category], index="kind_status_category"
                        )
                        .count()
                        .run(db.conn)
                    )

                result[category]["desktops"]["status"]["Other"] = (
                    r.table("domains")
                    .get_all(["desktop", category], index="kind_category")
                    .filter(
                        lambda desktop: r.not_(
                            r.expr(stable_status).contains(desktop["status"])
                        )
                    )
                    .count()
                    .run(db.conn)
                )

            # Process all template-related data
            for category in categories:
                result[category]["templates"]["total"] = (
                    r.table("domains")
                    .get_all(["template", category], index="kind_category")
                    .count()
                    .run(db.conn)
                )

                result[category]["templates"]["status"]["enabled"] = (
                    r.table("domains")
                    .get_all(
                        ["template", True, category], index="template_enabled_category"
                    )
                    .count()
                    .run(db.conn)
                )

                result[category]["templates"]["status"]["disabled"] = (
                    r.table("domains")
                    .get_all(
                        ["template", False, category], index="template_enabled_category"
                    )
                    .count()
                    .run(db.conn)
                )

        return result

    return _group_by_categories_cache.get(fetch)


def CategoriesKindState(kind, state=False):
    # Used by stats go
    cache_key = (kind, state)

    def fetch():
        query = {}
        with app.app_context():
            categories = list(r.table("categories").pluck("id")["id"].run(db.conn))

            for category in categories:
                if kind == "desktop":
                    if state:
                        if state == "Other":
                            count = (
                                r.table("domains")
                                .get_all(["desktop", category], index="kind_category")
                                .filter(
                                    lambda desktop: r.not_(
                                        r.expr(stable_status).contains(
                                            desktop["status"]
                                        )
                                    )
                                )
                                .count()
                                .run(db.conn)
                            )
                        else:
                            count = (
                                r.table("domains")
                                .get_all(
                                    ["desktop", state, category],
                                    index="kind_status_category",
                                )
                                .count()
                                .run(db.conn)
                            )
                        query[category] = {"desktops": {"status": {state: count}}}
                    else:
                        total = (
                            r.table("domains")
                            .get_all(["desktop", category], index="kind_category")
                            .count()
                            .run(db.conn)
                        )
                        status_counts = {}
                        for ds in stable_status:
                            status_counts[ds] = (
                                r.table("domains")
                                .get_all(
                                    ["desktop", ds, category],
                                    index="kind_status_category",
                                )
                                .count()
                                .run(db.conn)
                            )
                        status_counts["Other"] = (
                            r.table("domains")
                            .get_all(["desktop", category], index="kind_category")
                            .filter(
                                lambda desktop: r.not_(
                                    r.expr(stable_status).contains(desktop["status"])
                                )
                            )
                            .count()
                            .run(db.conn)
                        )
                        query[category] = {
                            "desktops": {
                                "total": total,
                                "status": status_counts,
                            }
                        }

                elif kind == "template":
                    if state == "enabled":
                        count = (
                            r.table("domains")
                            .get_all(
                                ["template", True, category],
                                index="template_enabled_category",
                            )
                            .count()
                            .run(db.conn)
                        )
                        query[category] = {"templates": {"status": {"enabled": count}}}
                    elif state == "disabled":
                        count = (
                            r.table("domains")
                            .get_all(
                                ["template", False, category],
                                index="template_enabled_category",
                            )
                            .count()
                            .run(db.conn)
                        )
                        query[category] = {"templates": {"status": {"disabled": count}}}
                    else:
                        total = (
                            r.table("domains")
                            .get_all(["template", category], index="kind_category")
                            .count()
                            .run(db.conn)
                        )
                        enabled = (
                            r.table("domains")
                            .get_all(
                                ["template", True, category],
                                index="template_enabled_category",
                            )
                            .count()
                            .run(db.conn)
                        )
                        disabled = (
                            r.table("domains")
                            .get_all(
                                ["template", False, category],
                                index="template_enabled_category",
                            )
                            .count()
                            .run(db.conn)
                        )
                        query[category] = {
                            "templates": {
                                "total": total,
                                "status": {
                                    "enabled": enabled,
                                    "disabled": disabled,
                                },
                            }
                        }

        return query

    return _categories_kind_state_cache.get(cache_key, fetch)


def CategoriesLimitsHardware():
    # Optimized: Uses 2 aggregated queries instead of 1 + (N × 3) queries
    def fetch():
        query = {}
        with app.app_context():
            # Query 1: Get all categories with limits
            categories = list(r.table("categories").pluck("id", "limits").run(db.conn))

            # Query 2: Single aggregated query for all started desktops
            try:
                started_stats = dict(
                    r.table("domains")
                    .get_all("desktop", index="kind")
                    .filter({"status": "Started"})
                    .group("category")
                    .map(
                        lambda domain: {
                            "count": 1,
                            "vcpus": domain["create_dict"]["hardware"]["vcpus"].default(
                                0
                            ),
                            "memory": domain["create_dict"]["hardware"][
                                "memory"
                            ].default(0),
                        }
                    )
                    .reduce(
                        lambda a, b: {
                            "count": a["count"].add(b["count"]),
                            "vcpus": a["vcpus"].add(b["vcpus"]),
                            "memory": a["memory"].add(b["memory"]),
                        }
                    )
                    .run(db.conn)
                )
            except r.ReqlNonExistenceError:
                started_stats = {}

        # Post-processing: Build result structure from aggregated data
        for category in categories:
            cat_id = category["id"]
            stats = started_stats.get(cat_id, {"count": 0, "vcpus": 0, "memory": 0})

            query[cat_id] = {
                "Started desktops": stats["count"],
                "vCPUs": {
                    "Limit": (
                        0
                        if category["limits"] == False
                        else category["limits"]["vcpus"]
                    ),
                    "Running": stats["vcpus"],
                },
                "Memory": {
                    "Limit": (
                        0
                        if category["limits"] == False
                        else category["limits"]["memory"]
                    ),
                    "Running": stats["memory"],
                },
            }

        return query

    return _categories_limits_hardware_cache.get(fetch)


def CategoriesDeploys():
    # Used by stats go
    # Optimized: Uses eq_join instead of merge+get (1 query vs N+1)
    def fetch():
        with app.app_context():
            return dict(
                r.table("deployments")
                .eq_join("user", r.table("users"))
                .group(lambda row: row["right"]["category"].default("None"))
                .count()
                .run(db.conn)
            )

    return _categories_deploys_cache.get(fetch)


def DomainsByCategoryCount():
    # Optimized: Pre-fetch categories instead of N lookups in map()
    def fetch():
        with app.app_context():
            # Query 1: Pre-fetch all category names (150 rows max)
            categories = {
                c["id"]: c["name"]
                for c in r.table("categories").pluck("id", "name").run(db.conn)
            }

            # Query 2: Main aggregation query
            domain_counts = list(
                r.table("domains")
                .get_all("desktop", index="kind")
                .group("category", "status")
                .count()
                .ungroup()
                .run(db.conn)
            )

        # Build result in Python (faster than N RethinkDB lookups)
        result = {}
        for item in domain_counts:
            category = item["group"][0]
            status = item["group"][1]
            count = item["reduction"]

            if category not in result:
                result[category] = {
                    "category": category,
                    "category_name": categories.get(category, category),
                    "desktops": [],
                }
            result[category]["desktops"].append({"status": status, "count": count})

        return list(result.values())

    return _domains_by_category_count_cache.get(fetch)
