from rethinkdb import RethinkDB

r = RethinkDB()
from cachetools import TTLCache, cached

from api import app

from ..libv2.flask_rethink import RDB

db = RDB(app)
db.init_app(app)

stable_status = ["Started", "Stopped", "Failed"]


@cached(cache=TTLCache(maxsize=1, ttl=5))
def Users():
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


@cached(cache=TTLCache(maxsize=1, ttl=30))
def desktops_total():
    with app.app_context():
        return r.table("domains").get_all("desktop", index="kind").count().run(db.conn)


@cached(cache=TTLCache(maxsize=1, ttl=1))
def Desktops():
    # Used by webapp desktops status
    with app.app_context():
        group_by_status = (
            r.table("domains")
            .get_all("desktop", index="kind")
            .group("status")
            .count()
            .run(db.conn)
        )
    return {
        "total": desktops_total(),
        "status": group_by_status,
    }


@cached(cache=TTLCache(maxsize=1, ttl=5))
def DomainsStatus():
    # Used by stats go
    with app.app_context():
        domains = r.table("domains").group(index="kind_status").count().run(db.conn)
    d = {}
    for k, v in domains.items():
        if k[0] not in d:
            d[k[0]] = {}
        d[k[0]][k[1]] = v
    return d


@cached(cache=TTLCache(maxsize=1, ttl=5))
def Templates():
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


@cached(cache=TTLCache(maxsize=1, ttl=5))
def OtherStatus():
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


@cached(cache=TTLCache(maxsize=5, ttl=5))
def Kind(kind):
    query = {}
    if kind == "desktops":
        query = r.table("domains").get_all("desktop", index="kind").pluck("id", "user")

    elif kind == "templates":
        query = r.table("domains").get_all("template", index="kind").pluck("id")

    elif kind == "users":
        query = r.table(kind).pluck("id", "role", "category", "group")

    elif kind == "hypervisors":
        query = r.table(kind).pluck("id", "status", "only_forced")

    with app.app_context():
        return list(query.run(db.conn))


@cached(cache=TTLCache(maxsize=1, ttl=30))
def GroupByCategories():
    # Used by stats go
    query = {}
    with app.app_context():
        categories = r.table("categories").pluck("id")["id"].run(db.conn)
    for category in categories:
        query[category] = {
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
                    "Unknown": "",
                    "Other": "",
                },
            },
            "templates": {
                "total": "",
                "status": {"enabled": "", "disabled": ""},
            },
        }
        with app.app_context():
            query[category]["users"]["total"] = (
                r.table("users")
                .get_all(category, index="category")
                .count()
                .run(db.conn)
            )
        with app.app_context():
            query[category]["users"]["status"]["enabled"] = (
                r.table("users")
                .get_all(category, index="category")
                .filter({"active": True})
                .count()
                .run(db.conn)
            )
        query[category]["users"]["status"]["disabled"] = (
            query[category]["users"]["total"]
            - query[category]["users"]["status"]["enabled"]
        )

        with app.app_context():
            query[category]["users"]["roles"] = (
                r.table("users")
                .get_all(category, index="category")
                .group("role")
                .count()
                .run(db.conn)
            )

        with app.app_context():
            query[category]["desktops"]["total"] = (
                r.table("domains")
                .get_all(["desktop", category], index="kind_category")
                .count()
                .run(db.conn)
            )
        for status in stable_status:
            with app.app_context():
                query[category]["desktops"]["status"][status] = (
                    r.table("domains")
                    .get_all(
                        ["desktop", status, category], index="kind_status_category"
                    )
                    .count()
                    .run(db.conn)
                )
        with app.app_context():
            query[category]["desktops"]["status"]["Other"] = (
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

        with app.app_context():
            query[category]["templates"]["total"] = (
                r.table("domains")
                .get_all(["template", category], index="kind_category")
                .count()
                .run(db.conn)
            )
        with app.app_context():
            query[category]["templates"]["status"]["enabled"] = (
                r.table("domains")
                .get_all(
                    ["template", True, category], index="template_enabled_category"
                )
                .count()
                .run(db.conn)
            )
        with app.app_context():
            query[category]["templates"]["status"]["disabled"] = (
                r.table("domains")
                .get_all(
                    ["template", False, category], index="template_enabled_category"
                )
                .count()
                .run(db.conn)
            )
    return query


@cached(cache=TTLCache(maxsize=1, ttl=30))
def CategoriesKindState(kind, state=False):
    # Used by stats go
    query = {}
    with app.app_context():
        categories = r.table("categories").pluck("id")["id"].run(db.conn)
    for category in categories:
        if kind == "desktop":
            if state:
                query[category] = {"desktops": {"status": {state: ""}}}
                with app.app_context():
                    query[category]["desktops"]["status"][state] = (
                        r.table("domains")
                        .get_all(
                            ["desktop", state, category],
                            index="kind_status_category",
                        )
                        .count()
                        .run(db.conn)
                    )
                if state == "Other":
                    with app.app_context():
                        query[category]["desktops"]["status"]["Other"] = (
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
                with app.app_context():
                    query[category]["desktops"]["total"] = (
                        r.table("domains")
                        .get_all(["desktop", category], index="kind_category")
                        .count()
                        .run(db.conn)
                    )

                for ds in stable_status:
                    with app.app_context():
                        query[category]["desktops"]["status"][ds] = (
                            r.table("domains")
                            .get_all(
                                ["desktop", ds, category],
                                index="kind_status_category",
                            )
                            .count()
                            .run(db.conn)
                        )
                with app.app_context():
                    query[category]["desktops"]["status"]["Other"] = (
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
                return query

        elif kind == "template":
            if state == "enabled":
                query[category] = {"templates": {"status": {"enabled": ""}}}
                with app.app_context():
                    query[category]["templates"]["status"]["enabled"] = (
                        r.table("domains")
                        .get_all(
                            ["template", True, category],
                            index="template_enabled_category",
                        )
                        .count()
                        .run(db.conn)
                    )
                return query

            elif state == "disabled":
                query[category] = {"templates": {"status": {"disabled": ""}}}
                with app.app_context():
                    query[category]["templates"]["status"]["disabled"] = (
                        r.table("domains")
                        .get_all(
                            ["template", False, category],
                            index="template_enabled_category",
                        )
                        .count()
                        .run(db.conn)
                    )
                return query

            else:
                query[category] = {
                    "templates": {
                        "total": "",
                        "status": {"enabled": "", "disabled": ""},
                    }
                }
                with app.app_context():
                    query[category]["templates"]["total"] = (
                        r.table("domains")
                        .get_all(["template", category], index="kind_category")
                        .count()
                        .run(db.conn)
                    )
                with app.app_context():
                    query[category]["templates"]["status"]["enabled"] = (
                        r.table("domains")
                        .get_all(
                            ["template", True, category],
                            index="template_enabled_category",
                        )
                        .count()
                        .run(db.conn)
                    )
                with app.app_context():
                    query[category]["templates"]["status"]["disabled"] = (
                        r.table("domains")
                        .get_all(
                            ["template", False, category],
                            index="template_enabled_category",
                        )
                        .count()
                        .run(db.conn)
                    )
                return query


@cached(cache=TTLCache(maxsize=1, ttl=30))
def CategoriesLimitsHardware():
    query = {}
    with app.app_context():
        categories = r.table("categories").pluck("id", "limits").run(db.conn)

    for category in categories:
        query[category["id"]] = {
            "Started desktops": "",
            "vCPUs": {"Limit": "", "Running": ""},
            "Memory": {"Limit": "", "Running": ""},
        }
        with app.app_context():
            query[category["id"]]["Started desktops"] = (
                r.table("domains")
                .get_all(
                    ["desktop", "Started", category["id"]], index="kind_status_category"
                )
                .count()
                .run(db.conn)
            )

        # If unlimited
        if category["limits"] == False:
            query[category["id"]]["vCPUs"]["Limit"] = 0
            query[category["id"]]["Memory"]["Limit"] = 0
        else:
            query[category["id"]]["vCPUs"]["Limit"] = category["limits"]["vcpus"]
            query[category["id"]]["Memory"]["Limit"] = category["limits"]["memory"]

        with app.app_context():
            query[category["id"]]["vCPUs"]["Running"] = (
                r.table("domains")
                .get_all(
                    ["desktop", "Started", category["id"]], index="kind_status_category"
                )["create_dict"]["hardware"]["vcpus"]
                .sum()
                .run(db.conn)
            )
        with app.app_context():
            query[category["id"]]["Memory"]["Running"] = (
                r.table("domains")
                .get_all(
                    ["desktop", "Started", category["id"]], index="kind_status_category"
                )["create_dict"]["hardware"]["memory"]
                .sum()
                .run(db.conn)
            )
    return query


@cached(cache=TTLCache(maxsize=1, ttl=5))
def CategoriesDeploys():
    # Used by stats go
    with app.app_context():
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
            .run(db.conn)
        )


@cached(cache=TTLCache(maxsize=1, ttl=30))
def DomainsByCategoryCount():
    with app.app_context():
        return (
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
                    "category_name": r.table("categories").get(doc["group"])["name"],
                    "desktops": doc["reduction"].without("category"),
                }
            )
            .run(db.conn)
        )
