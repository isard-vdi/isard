from rethinkdb import RethinkDB

from ..auth.authentication import *

r = RethinkDB()
from api import app

from ..libv2.flask_rethink import RDB

db = RDB(app)
db.init_app(app)


def Users():
    with app.app_context():
        return {
            "total": r.table("users").count().run(db.conn),
            "status": {
                "enabled": r.table("users")
                .get_all(True, index="active")
                .count()
                .run(db.conn),
                "disabled": r.table("users")
                .get_all(False, index="active")
                .count()
                .run(db.conn),
            },
            "roles": r.table("users").group("role").count().run(db.conn),
        }


def Desktops():
    with app.app_context():
        desktop_status = ["Started", "Stopped", "Failed", "Unknown"]
        return {
            "total": r.table("domains")
            .get_all("desktop", index="kind")
            .count()
            .run(db.conn),
            "status": {
                "Started": r.table("domains")
                .get_all(["desktop", "Started"], index="kind_status")
                .count()
                .run(db.conn),
                "Stopped": r.table("domains")
                .get_all(["desktop", "Stopped"], index="kind_status")
                .count()
                .run(db.conn),
                "Failed": r.table("domains")
                .get_all(["desktop", "Failed"], index="kind_status")
                .count()
                .run(db.conn),
                "Unknown": r.table("domains")
                .get_all(["desktop", "Unknown"], index="kind_status")
                .count()
                .run(db.conn),
                "Other": r.table("domains")
                .get_all("desktop", index="kind")
                .filter(
                    lambda desktop: r.not_(
                        r.expr(desktop_status).contains(desktop["status"])
                    )
                )
                .count()
                .run(db.conn),
            },
        }


def Templates():
    with app.app_context():
        return {
            "total": r.table("domains")
            .get_all("template", index="kind")
            .count()
            .run(db.conn),
            "status": {
                "enabled": r.table("domains")
                .get_all("template", index="kind")
                .filter({"enabled": True})
                .count()
                .run(db.conn),
                "disabled": r.table("domains")
                .get_all("template", index="kind")
                .filter({"enabled": False})
                .count()
                .run(db.conn),
            },
        }


def OtherStatus():
    with app.app_context():
        query = {}
        categories = r.table("categories")["id"].run(db.conn)
        status = [
            "Creating",
            "CreatingAndStarting",
            "CreatingDisk",
            "CreatingDiskFromScratch",
            "CreatingDomain",
            "CreatingDomainFromBuilder",
            "CreatingDomainFromDisk",
            "CreatingFromBuilder",
            "CreatingNewTemplateInDB",
            "CreatingTemplateDisk",
            "CreatingTemplate",
            "Deleting",
            "DeletingDomainDisk",
            "DiskDeleted",
            "Failed",
            "FailedDeleted",
            "Resumed",
            "RunningVirtBuilder",
            "Shutting-down",
            "Starting",
            "StartingDomainDisposable",
            "StartingPaused",
            "Stopping",
            "StoppingAndDeleting",
            "Suspended",
            "TemplateDiskCreated",
            "Unknown",
            "Updating",
        ]
        for category in categories:
            query[category] = {
                "desktops_wrong_status": {
                    "Creating": "",
                    "CreatingAndStarting": "",
                    "CreatingDisk": "",
                    "CreatingDiskFromScratch": "",
                    "CreatingDomain": "",
                    "CreatingDomainFromBuilder": "",
                    "CreatingDomainFromDisk": "",
                    "CreatingFromBuilder": "",
                    "CreatingNewTemplateInDB": "",
                    "CreatingTemplateDisk": "",
                    "CreatingTemplate": "",
                    "Deleting": "",
                    "DeletingDomainDisk": "",
                    "DiskDeleted": "",
                    "Failed": "",
                    "FailedDeleted": "",
                    "Resumed": "",
                    "RunningVirtBuilder": "",
                    "Shutting-down": "",
                    "Starting": "",
                    "StartingDomainDisposable": "",
                    "StartingPaused": "",
                    "Stopping": "",
                    "StoppingAndDeleting": "",
                    "Suspended": "",
                    "TemplateDiskCreated": "",
                    "Unknown": "",
                    "Updating": "",
                },
                "templates_wrong_status": {
                    "Creating": "",
                    "CreatingAndStarting": "",
                    "CreatingDisk": "",
                    "CreatingDiskFromScratch": "",
                    "CreatingDomain": "",
                    "CreatingDomainFromBuilder": "",
                    "CreatingDomainFromDisk": "",
                    "CreatingFromBuilder": "",
                    "CreatingNewTemplateInDB": "",
                    "CreatingTemplateDisk": "",
                    "CreatingTemplate": "",
                    "Deleting": "",
                    "DeletingDomainDisk": "",
                    "DiskDeleted": "",
                    "Failed": "",
                    "FailedDeleted": "",
                    "Resumed": "",
                    "RunningVirtBuilder": "",
                    "Shutting-down": "",
                    "Starting": "",
                    "StartingDomainDisposable": "",
                    "StartingPaused": "",
                    "Stopping": "",
                    "StoppingAndDeleting": "",
                    "Suspended": "",
                    "TemplateDiskCreated": "",
                    "Unknown": "",
                    "Updating": "",
                },
            }
            for s in status:
                query[category]["desktops_wrong_status"][s] = (
                    r.table("domains")
                    .get_all(["desktop", s, category], index="kind_status_category")
                    .count()
                    .run(db.conn)
                )
                query[category]["templates_wrong_status"][s] = (
                    r.table("domains")
                    .get_all(["template", s, category], index="kind_status_category")
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
                if state == "Other":
                    return {
                        "desktops": {
                            "status": {
                                "Other": r.table("domains")
                                .get_all("desktop", index="kind")
                                .filter(
                                    lambda desktop: r.not_(
                                        r.expr(desktop_status).contains(
                                            desktop["status"]
                                        )
                                    )
                                )
                                .count()
                                .run(db.conn)
                            }
                        }
                    }
                else:
                    return {
                        "desktops": {
                            "status": {
                                state: r.table("domains")
                                .get_all(["desktop", state], index="kind_status")
                                .count()
                                .run(db.conn)
                            }
                        }
                    }

            else:
                return {
                    "desktops": {
                        "total": r.table("domains")
                        .get_all("desktop", index="kind")
                        .count()
                        .run(db.conn),
                        "status": {
                            "Started": r.table("domains")
                            .get_all(["desktop", "Started"], index="kind_status")
                            .count()
                            .run(db.conn),
                            "Stopped": r.table("domains")
                            .get_all(["desktop", "Stopped"], index="kind_status")
                            .count()
                            .run(db.conn),
                            "Failed": r.table("domains")
                            .get_all(["desktop", "Failed"], index="kind_status")
                            .count()
                            .run(db.conn),
                            "Unknown": r.table("domains")
                            .get_all(["desktop", "Unknown"], index="kind_status")
                            .count()
                            .run(db.conn),
                            "Other": r.table("domains")
                            .get_all("desktop", index="kind")
                            .filter(
                                lambda desktop: r.not_(
                                    r.expr(desktop_status).contains(desktop["status"])
                                )
                            )
                            .count()
                            .run(db.conn),
                        },
                    }
                }

        elif kind == "template":
            if state:
                if state == "enabled":
                    return {
                        "templates": {
                            "enabled": r.table("domains")
                            .get_all("template", index="kind")
                            .filter({"enabled": True})
                            .count()
                            .run(db.conn)
                        }
                    }
                elif state == "disabled":
                    return {
                        "templates": {
                            "disabled": r.table("domains")
                            .get_all("template", index="kind")
                            .filter({"enabled": False})
                            .count()
                            .run(db.conn)
                        }
                    }
            else:
                return {
                    "templates": {
                        "total": r.table("domains")
                        .get_all("template", index="kind")
                        .count()
                        .run(db.conn),
                        "status": {
                            "enabled": r.table("domains")
                            .get_all("template", index="kind")
                            .filter({"enabled": True})
                            .count()
                            .run(db.conn),
                            "disabled": r.table("domains")
                            .get_all("template", index="kind")
                            .filter({"enabled": False})
                            .count()
                            .run(db.conn),
                        },
                    }
                }


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
                r.table("users")
                .get_all(category, index="category")
                .count()
                .run(db.conn)
            )
            query[category]["users"]["status"]["enabled"] = (
                r.table("users")
                .get_all(category, index="category")
                .filter({"active": True})
                .count()
                .run(db.conn)
            )
            query[category]["users"]["status"]["disabled"] = (
                r.table("users")
                .get_all(category, index="category")
                .filter({"active": False})
                .count()
                .run(db.conn)
            )
            for role in user_role:
                query[category]["users"]["roles"][role] = (
                    r.table("users")
                    .get_all(category, index="category")
                    .filter({"role": role})
                    .count()
                    .run(db.conn)
                )

            query[category]["desktops"]["total"] = (
                r.table("domains")
                .get_all(["desktop", category], index="kind_category")
                .count()
                .run(db.conn)
            )
            for status in desktop_status:
                query[category]["desktops"]["status"][status] = (
                    r.table("domains")
                    .get_all(
                        ["desktop", status, category], index="kind_status_category"
                    )
                    .count()
                    .run(db.conn)
                )
            query[category]["desktops"]["status"]["Other"] = (
                r.table("domains")
                .get_all(["desktop", category], index="kind_category")
                .filter(
                    lambda desktop: r.not_(
                        r.expr(desktop_status).contains(desktop["status"])
                    )
                )
                .count()
                .run(db.conn)
            )

            query[category]["templates"]["total"] = (
                r.table("domains")
                .get_all(["template", category], index="kind_category")
                .count()
                .run(db.conn)
            )
            query[category]["templates"]["status"]["enabled"] = (
                r.table("domains")
                .get_all(["template", category], index="kind_category")
                .filter({"enabled": True})
                .count()
                .run(db.conn)
            )
            query[category]["templates"]["status"]["disabled"] = (
                r.table("domains")
                .get_all(["template", category], index="kind_category")
                .filter({"enabled": False})
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
                    query[category] = {"desktops": {"status": {state: ""}}}
                    query[category]["desktops"]["status"][state] = (
                        r.table("domains")
                        .get_all(
                            ["desktop", state, category], index="kind_status_category"
                        )
                        .count()
                        .run(db.conn)
                    )
                    if state == "Other":
                        query[category]["desktops"]["status"]["Other"] = (
                            r.table("domains")
                            .get_all(["desktop", category], index="kind_category")
                            .filter(
                                lambda desktop: r.not_(
                                    r.expr(desktop_status).contains(desktop["status"])
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
                    query[category]["desktops"]["total"] = (
                        r.table("domains")
                        .get_all(["desktop", category], index="kind_category")
                        .count()
                        .run(db.conn)
                    )

                    for ds in desktop_status:
                        query[category]["desktops"]["status"][ds] = (
                            r.table("domains")
                            .get_all(
                                ["desktop", ds, category], index="kind_status_category"
                            )
                            .count()
                            .run(db.conn)
                        )
                    query[category]["desktops"]["status"]["Other"] = (
                        r.table("domains")
                        .get_all(["desktop", category], index="kind_category")
                        .filter(
                            lambda desktop: r.not_(
                                r.expr(desktop_status).contains(desktop["status"])
                            )
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
                        .get_all(["template", category], index="kind_category")
                        .filter({"enabled": True})
                        .count()
                        .run(db.conn)
                    )
                    return query

                elif state == "disabled":
                    query[category] = {"templates": {"status": {"disabled": ""}}}
                    query[category]["templates"]["status"]["disabled"] = (
                        r.table("domains")
                        .get_all(["template", category], index="kind_category")
                        .filter({"enabled": False})
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
                        .get_all(["template", category], index="kind_category")
                        .count()
                        .run(db.conn)
                    )
                    query[category]["templates"]["status"]["enabled"] = (
                        r.table("domains")
                        .get_all(["template", category], index="kind_category")
                        .filter({"enabled": True})
                        .count()
                        .run(db.conn)
                    )
                    query[category]["templates"]["status"]["disabled"] = (
                        r.table("domains")
                        .get_all(["template", category], index="kind_category")
                        .filter({"enabled": False})
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

            query[category["id"]]["vCPUs"]["Running"] = (
                r.table("domains")
                .get_all(
                    ["desktop", "Started", category["id"]], index="kind_status_category"
                )["create_dict"]["hardware"]["vcpus"]
                .sum()
                .run(db.conn)
            )
            query[category["id"]]["Memory"]["Running"] = (
                r.table("domains")
                .get_all(
                    ["desktop", "Started", category["id"]], index="kind_status_category"
                )["create_dict"]["hardware"]["memory"]
                .sum()
                .run(db.conn)
            )
    return query
