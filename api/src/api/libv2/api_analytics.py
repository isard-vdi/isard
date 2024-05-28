#
#   Copyright © 2023 Miriam Melina Gamboa Valdez
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

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)


def storage_usage(categories=None):
    storage = {}
    if categories:
        with app.app_context():
            storage["media"] = (
                r.table("media")
                .get_all(r.args(categories), index="category")
                .filter(r.row["status"].ne("deleted"))
                .pluck({"progress": "total_bytes"})
                .sum(lambda size: size["progress"]["total_bytes"].default(0))
                .run(db.conn)
            ) / 1073741824
            storage["domains"] = (
                r.table("users")
                .get_all(r.args(categories), index="category")
                .pluck("id")
                .merge(
                    lambda user: {
                        "storage": r.table("storage")
                        .get_all(
                            [user["id"], "ready"],
                            index="user_status",
                        )
                        .pluck({"qemu-img-info": {"actual-size": True}})
                        .default({"qemu-img-info": {"actual-size": 0}})
                        .sum(
                            lambda right: right["qemu-img-info"]["actual-size"].default(
                                0
                            )
                        ),
                    }
                )
                .sum("storage")
                / 1073741824
            ).run(db.conn)
    else:
        with app.app_context():
            storage["media"] = (
                r.table("media")
                .filter(r.row["status"].ne("deleted"))
                .pluck({"progress": "total_bytes"})
                .sum(lambda size: size["progress"]["total_bytes"].default(0))
                .run(db.conn)
            ) / 1073741824
            storage["domains"] = (
                r.table("users")
                .pluck("id")
                .merge(
                    lambda user: {
                        "storage": r.table("storage")
                        .get_all(
                            [user["id"], "ready"],
                            index="user_status",
                        )
                        .pluck({"qemu-img-info": "actual-size"})
                        .default({"qemu-img-info": {"actual-size": 0}})
                        .sum(
                            lambda right: right["qemu-img-info"]["actual-size"].default(
                                0
                            )
                        ),
                    }
                )
                .sum("storage")
                / 1073741824
            ).run(db.conn)

    return storage


def resource_count(categories=None):
    count = {}
    if categories:
        with app.app_context():
            count["desktops"] = (
                r.table("domains")
                .get_all(r.args(categories), index="category")
                .filter({"kind": "desktop"})
                .count()
                .run(db.conn)
            )
            count["templates"] = (
                r.table("domains")
                .get_all(r.args(categories), index="category")
                .filter({"kind": "template"})
                .count()
                .run(db.conn)
            )
            count["media"] = (
                r.table("media")
                .get_all(r.args(categories), index="category")
                .filter(r.row["status"].ne("deleted"))
                .count()
                .run(db.conn)
            )
            count["users"] = (
                r.table("users")
                .get_all(r.args(categories), index="category")
                .count()
                .run(db.conn)
            )
            count["groups"] = (
                r.table("groups")
                .get_all(r.args(categories), index="parent_category")
                .count()
                .run(db.conn)
            )
            count["deployments"] = (
                r.table("deployments")
                .eq_join("user", r.table("users"))
                .filter(
                    lambda deployment: r.expr(categories).contains(
                        deployment["right"]["category"]
                    )
                )
                .count()
                .run(db.conn)
            )
    else:
        with app.app_context():
            count["desktops"] = (
                r.table("domains").get_all("desktop", index="kind").count().run(db.conn)
            )
            count["templates"] = (
                r.table("domains")
                .get_all("template", index="kind")
                .count()
                .run(db.conn)
            )
            count["media"] = (
                r.table("media")
                .filter(r.row["status"].ne("deleted"))
                .count()
                .run(db.conn)
            )
            count["users"] = r.table("users").count().run(db.conn)
            count["groups"] = r.table("groups").count().run(db.conn)
            count["deployments"] = r.table("deployments").count().run(db.conn)

    return count


def suggested_removals(categories=None, months_without_use=6):
    suggestions = {"empty_deployments": {}, "unused_desktops": {}}
    empty_deployments_query = r.table("deployments").eq_join("user", r.table("users"))
    unused_desktops_query = r.table("domains")
    if categories:
        empty_deployments_query = empty_deployments_query.filter(
            lambda deployment: r.expr(categories).contains(
                deployment["right"]["category"]
            )
        )
        unused_desktops_query = unused_desktops_query.get_all(
            r.args(categories), index="category"
        ).filter(lambda row: (row["kind"] == "desktop") & (~row["server"]))
    else:
        unused_desktops_query = unused_desktops_query.get_all(
            "desktop", index="kind"
        ).filter(lambda row: ~row["server"])

    empty_deployments_query = (
        empty_deployments_query.pluck(
            {
                "left": True,
                "right": ["group", "category", "username"],
            }
        )
        .zip()
        .merge(
            lambda deployment: {
                "domains": r.table("domains")
                .get_all(deployment["id"], index="tag")
                .count(),
                "category_name": r.table("categories").get(deployment["category"])[
                    "name"
                ],
                "group_name": r.table("groups").get(deployment["group"])["name"],
            }
        )
        .filter({"domains": 0})
    )
    unused_desktops_query = (
        unused_desktops_query.merge(
            lambda desktop: {
                "logs": r.table("logs_desktops")
                .get_all(desktop["id"], index="desktop_id")
                .filter(
                    lambda log: r.expr(
                        ["desktop-owner", "deployment-owner", "desktop-directviewer"]
                    ).contains(log["starting_by"])
                )
                .count(),
                "logs_between": r.table("logs_desktops")
                .get_all(desktop["id"], index="desktop_id")
                .filter(
                    lambda log: r.expr(
                        ["desktop-owner", "deployment-owner", "desktop-directviewer"]
                    ).contains(log["starting_by"])
                )
                .filter(
                    lambda log: log["starting_time"].during(
                        r.now().sub(r.expr(60 * 60 * 24 * 30 * months_without_use)),
                        r.now(),
                    )
                )
                .count(),
            }
        )
        .filter(lambda desktop: (desktop["logs"] == 0) | (desktop["logs_between"] == 0))
        .eq_join(
            r.row["create_dict"]["hardware"]["disks"][0]["storage_id"],
            r.table("storage"),
        )
        .without({"right": {"id": True}})
        .zip()
        .merge(
            lambda desktop: {
                # "last_log": r.table("logs_desktops")
                # .get_all(desktop["id"], index="desktop_id")
                # .order_by(r.desc("starting_time"))
                # .nth(-1),
                "category_name": r.table("categories")
                .get(desktop["category"])
                .default({"name": "[DELETED] " + desktop["category"]})["name"],
                "group_name": r.table("groups")
                .get(desktop["group"])
                .default({"name": "[DELETED] " + desktop["group"]})["name"],
                "size": desktop["qemu-img-info"]["actual-size"].default(0) / 1073741824,
            }
        )
        .pluck("id", "name", "category_name", "group_name", "username", "size")
    )
    with app.app_context():
        suggestions["empty_deployments"] = list(empty_deployments_query.run(db.conn))
        suggestions["unused_desktops"]["desktops"] = list(
            unused_desktops_query.run(db.conn)
        )
        unused_desktops_ids = [
            desktop["id"] for desktop in suggestions["unused_desktops"]["desktops"]
        ]
        suggestions["unused_desktops"]["size"] = (
            r.table("domains")
            .get_all(r.args(unused_desktops_ids))
            .eq_join(
                r.row["create_dict"]["hardware"]["disks"][0]["storage_id"],
                r.table("storage"),
            )
            .zip()
            .pluck({"qemu-img-info": "actual-size"})
            .default({"qemu-img-info": {"actual-size": 0}})["qemu-img-info"][
                "actual-size"
            ]
            .sum(lambda size: size.default(0))
            .run(db.conn)
        ) / 1073741824

    return suggestions


def get_usage_graphs_conf():
    with app.app_context():
        return list(
            r.table("analytics")
            .merge(
                lambda conf: {
                    "grouping_name": r.branch(
                        r.table("usage_grouping").get(conf["grouping"]).ne(None),
                        r.table("usage_grouping").get(conf["grouping"])["name"],
                        conf["grouping"],
                    )
                }
            )
            .run(db.conn)
        )


def get_usage_graph_conf(graph_conf_id):
    with app.app_context():
        return r.table("analytics").get(graph_conf_id).run(db.conn)


def add_usage_graph_conf(data):
    with app.app_context():
        r.table("analytics").insert(data).run(db.conn)


def update_usage_graph_conf(graph_conf_id, data):
    with app.app_context():
        r.table("analytics").get(graph_conf_id).update(data).run(db.conn)


def delete_usage_graph_conf(graph_conf_id):
    with app.app_context():
        r.table("analytics").get(graph_conf_id).delete().run(db.conn)
