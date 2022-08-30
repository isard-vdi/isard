from rethinkdb import RethinkDB

from ..auth.authentication import *

r = RethinkDB()
from api import app

from ..libv2.flask_rethink import RDB

db = RDB(app)
db.init_app(app)
import logging as log


def Users():
    with app.app_context():
        query = {
            "users": {
                "total": "",
                "status": {"enabled": "", "disabled": ""},
                "roles": {},
            }
        }
        query["users"]["total"] = r.table("users").count().run(db.conn)

        query["users"]["status"]["enabled"] = (
            r.table("users").filter({"active": True}).count().run(db.conn)
        )
        query["users"]["status"]["disabled"] = (
            r.table("users").filter({"active": False}).count().run(db.conn)
        )

        user_roles = ["admin", "manager", "advanced", "user"]
        for role in user_roles:
            query["users"]["roles"][role] = (
                r.table("users").filter({"role": role}).count().run(db.conn)
            )
    return query


def Desktops():
    with app.app_context():
        query = {
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
        query["desktops"]["total"] = (
            r.table("domains").filter({"kind": "desktop"}).count().run(db.conn)
        )

        desktop_status = ["Started", "Stopped", "Failed", "Unknown"]
        for status in desktop_status:
            query["desktops"]["status"][status] = (
                r.table("domains")
                .filter({"kind": "desktop", "status": status})
                .count()
                .run(db.conn)
            )
        query["desktops"]["status"]["Other"] = (
            r.table("domains")
            .filter(
                lambda desktop: r.not_(
                    r.expr(desktop_status).contains(desktop["status"])
                )
                & (desktop["kind"] == "desktop")
            )
            .count()
            .run(db.conn)
        )

    return query


def Templates():
    with app.app_context():
        query = {"templates": {"total": "", "status": {"enabled": "", "disabled": ""}}}
        query["templates"]["total"] = (
            r.table("domains").filter({"kind": "template"}).count().run(db.conn)
        )

        query["templates"]["status"]["enabled"] = (
            r.table("domains")
            .filter({"kind": "template", "enabled": True})
            .count()
            .run(db.conn)
        )
        query["templates"]["status"]["disabled"] = (
            r.table("domains")
            .filter({"kind": "template", "enabled": False})
            .count()
            .run(db.conn)
        )

    return query


def KindState(kind, state=False):
    with app.app_context():
        query = {}
        desktop_status = ["Started", "Stopped", "Failed", "Unknown"]
        if kind == "desktop":
            if state:
                query = {"desktops": {"status": {state: ""}}}
                query["desktops"]["status"][state] = (
                    r.table("domains")
                    .filter(
                        {
                            "kind": "desktop",
                            "status": state,
                        }
                    )
                    .count()
                    .run(db.conn)
                )
                return query
            else:
                query = {
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
                query["desktops"]["total"] = (
                    r.table("domains").filter({"kind": "desktop"}).count().run(db.conn)
                )

                for ds in desktop_status:
                    query["desktops"]["status"][ds] = (
                        r.table("domains")
                        .filter(
                            {
                                "kind": "desktop",
                                "status": ds,
                            }
                        )
                        .count()
                        .run(db.conn)
                    )
                query["desktops"]["status"]["Other"] = (
                    r.table("domains")
                    .filter(
                        lambda desktop: r.not_(
                            r.expr(desktop_status).contains(desktop["status"])
                        )
                        & (desktop["kind"] == "desktop")
                    )
                    .count()
                    .run(db.conn)
                )
                return query

        elif kind == "template":
            if state:
                if state == "enabled":
                    query = {"templates": {"status": {"enabled": ""}}}
                    query["templates"]["status"]["enabled"] = (
                        r.table("domains")
                        .filter(
                            {
                                "kind": "template",
                                "enabled": True,
                            }
                        )
                        .count()
                        .run(db.conn)
                    )
                    return query
                elif state == "disabled":
                    query = {"templates": {"status": {"disabled": ""}}}
                    query["templates"]["status"]["disabled"] = (
                        r.table("domains")
                        .filter(
                            {
                                "kind": "template",
                                "enabled": False,
                            }
                        )
                        .count()
                        .run(db.conn)
                    )
                    return query
            else:
                query = {
                    "templates": {
                        "total": "",
                        "status": {"enabled": "", "disabled": ""},
                    }
                }
                query["templates"]["total"] = (
                    r.table("domains").filter({"kind": "template"}).count().run(db.conn)
                )
                query["templates"]["status"]["enabled"] = (
                    r.table("domains")
                    .filter(
                        {
                            "kind": "template",
                            "enabled": True,
                        }
                    )
                    .count()
                    .run(db.conn)
                )
                query["templates"]["status"]["disabled"] = (
                    r.table("domains")
                    .filter(
                        {
                            "kind": "template",
                            "enabled": False,
                        }
                    )
                    .count()
                    .run(db.conn)
                )
                return query


def GroupByCategories():
    with app.app_context():
        query = {}
        categories = r.table("categories").pluck("id")["id"].run(db.conn)
        user_role = ["admin", "manager", "advanced", "user"]
        desktop_status = ["Started", "Stopped", "Failed", "Unknown"]
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
            query[category]["users"]["total"] = (
                r.table("users").filter({"category": category}).count().run(db.conn)
            )
            query[category]["users"]["status"]["enabled"] = (
                r.table("users")
                .filter({"category": category, "active": True})
                .count()
                .run(db.conn)
            )
            query[category]["users"]["status"]["disabled"] = (
                r.table("users")
                .filter({"category": category, "active": False})
                .count()
                .run(db.conn)
            )
            for role in user_role:
                query[category]["users"]["roles"][role] = (
                    r.table("users")
                    .filter({"category": category, "role": role})
                    .count()
                    .run(db.conn)
                )

            query[category]["desktops"]["total"] = (
                r.table("domains")
                .filter({"kind": "desktop", "category": category})
                .count()
                .run(db.conn)
            )
            for status in desktop_status:
                query[category]["desktops"]["status"][status] = (
                    r.table("domains")
                    .filter({"kind": "desktop", "category": category, "status": status})
                    .count()
                    .run(db.conn)
                )
            query[category]["desktops"]["status"]["Other"] = (
                r.table("domains")
                .filter(
                    lambda desktop: r.not_(
                        r.expr(desktop_status).contains(desktop["status"])
                    )
                    & (desktop["category"] == category)
                    & (desktop["kind"] == "desktop")
                )
                .count()
                .run(db.conn)
            )

            query[category]["templates"]["total"] = (
                r.table("domains")
                .filter({"kind": "template", "category": category})
                .count()
                .run(db.conn)
            )
            query[category]["templates"]["status"]["enabled"] = (
                r.table("domains")
                .filter({"kind": "template", "category": category, "enabled": True})
                .count()
                .run(db.conn)
            )
            query[category]["templates"]["status"]["disabled"] = (
                r.table("domains")
                .filter({"kind": "template", "category": category, "enabled": False})
                .count()
                .run(db.conn)
            )
    return query


def CategoriesKindState(kind, state=False):
    with app.app_context():
        query = {}
        categories = r.table("categories").pluck("id")["id"].run(db.conn)
        desktop_status = ["Started", "Stopped", "Failed", "Unknown"]
        for category in categories:
            if kind == "desktop":
                if state:
                    query[category] = {"desktops": {"status": {state}}}
                    query[category]["desktops"]["status"][state] = (
                        r.table("domains")
                        .filter(
                            {
                                "kind": "desktop",
                                "category": category,
                                "status": state,
                            }
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
                    query[category]["desktops"]["total"] = (
                        r.table("domains")
                        .filter({"kind": "desktop", "category": category})
                        .count()
                        .run(db.conn)
                    )

                    for ds in desktop_status:
                        query[category]["desktops"]["status"][ds] = (
                            r.table("domains")
                            .filter(
                                {
                                    "kind": "desktop",
                                    "category": category,
                                    "status": ds,
                                }
                            )
                            .count()
                            .run(db.conn)
                        )
                    query[category]["desktops"]["status"]["Other"] = (
                        r.table("domains")
                        .filter(
                            lambda desktop: r.not_(
                                r.expr(desktop_status).contains(desktop["status"])
                            )
                            & (desktop["category"] == category)
                            & (desktop["kind"] == "desktop")
                        )
                        .count()
                        .run(db.conn)
                    )
                    return query

            elif kind == "template":
                if state == "enabled":
                    query[category] = {"templates": {"status": {"enabled": ""}}}
                    query[category]["templates"]["status"]["enabled"] = (
                        r.table("domains")
                        .filter(
                            {
                                "kind": "template",
                                "category": category,
                                "enabled": True,
                            }
                        )
                        .count()
                        .run(db.conn)
                    )
                    return query

                elif state == "disabled":
                    query[category] = {"templates": {"status": {"disabled": ""}}}
                    query[category]["templates"]["status"]["disabled"] = (
                        r.table("domains")
                        .filter(
                            {
                                "kind": "template",
                                "category": category,
                                "enabled": False,
                            }
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
                    query[category]["templates"]["total"] = (
                        r.table("domains")
                        .filter({"kind": "template", "category": category})
                        .count()
                        .run(db.conn)
                    )
                    query[category]["templates"]["status"]["enabled"] = (
                        r.table("domains")
                        .filter(
                            {
                                "kind": "template",
                                "category": category,
                                "enabled": True,
                            }
                        )
                        .count()
                        .run(db.conn)
                    )
                    query[category]["templates"]["status"]["disabled"] = (
                        r.table("domains")
                        .filter(
                            {
                                "kind": "template",
                                "category": category,
                                "enabled": False,
                            }
                        )
                        .count()
                        .run(db.conn)
                    )
                    return query


def CategoriesLimitsHardware():
    with app.app_context():
        query = {}
        categories = r.table("categories").pluck("id", "limits").run(db.conn)

        for category in categories:
            query[category["id"]] = {
                "Started desktops": "",
                "vCPUs": {"Limit": "", "Running": ""},
                "Memory": {"Limit": "", "Running": ""},
            }
            query[category["id"]]["Started desktops"] = (
                r.table("domains")
                .filter(
                    {"kind": "desktop", "category": category["id"], "status": "Started"}
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

            query[category["id"]]["vCPUs"]["Running"] = (
                r.table("domains")
                .filter(
                    {"kind": "desktop", "category": category["id"], "status": "Started"}
                )["create_dict"]["hardware"]["vcpus"]
                .sum()
                .run(db.conn)
            )
            query[category["id"]]["Memory"]["Running"] = (
                r.table("domains")
                .filter(
                    {"kind": "desktop", "category": category["id"], "status": "Started"}
                )["create_dict"]["hardware"]["memory"]
                .sum()
                .run(db.conn)
            )
    return query
