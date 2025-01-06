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

from cachetools import TTLCache, cached
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)


@cached(
    cache=TTLCache(maxsize=10, ttl=30),
    key=lambda categories: frozenset(categories) if categories else (),
)
def storage_usage(categories=[]):
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
            ) / 10737418240
        with app.app_context():
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
        with app.app_context():
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


@cached(
    cache=TTLCache(maxsize=10, ttl=30),
    key=lambda categories: frozenset(categories) if categories else (),
)
def resource_count(categories=[]):
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
        with app.app_context():
            count["templates"] = (
                r.table("domains")
                .get_all(r.args(categories), index="category")
                .filter({"kind": "template"})
                .count()
                .run(db.conn)
            )
        with app.app_context():
            count["media"] = (
                r.table("media")
                .get_all(r.args(categories), index="category")
                .filter(r.row["status"].ne("deleted"))
                .count()
                .run(db.conn)
            )
        with app.app_context():
            count["users"] = (
                r.table("users")
                .get_all(r.args(categories), index="category")
                .count()
                .run(db.conn)
            )
        with app.app_context():
            count["groups"] = (
                r.table("groups")
                .get_all(r.args(categories), index="parent_category")
                .count()
                .run(db.conn)
            )
        with app.app_context():
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
        with app.app_context():
            count["templates"] = (
                r.table("domains")
                .get_all("template", index="kind")
                .count()
                .run(db.conn)
            )
        with app.app_context():
            count["media"] = (
                r.table("media")
                .filter(r.row["status"].ne("deleted"))
                .count()
                .run(db.conn)
            )
        with app.app_context():
            count["users"] = r.table("users").count().run(db.conn)
        with app.app_context():
            count["groups"] = r.table("groups").count().run(db.conn)
        with app.app_context():
            count["deployments"] = r.table("deployments").count().run(db.conn)

    return count


@cached(
    cache=TTLCache(maxsize=10, ttl=30),
    key=lambda categories: frozenset(categories) if categories else (),
)
def get_empty_deployments(categories=[]):
    empty_deployments_query = r.table("deployments").eq_join("user", r.table("users"))

    if categories:
        empty_deployments_query = empty_deployments_query.filter(
            lambda deployment: r.expr(categories).contains(
                deployment["right"]["category"]
            )
        )

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

    with app.app_context():
        return list(empty_deployments_query.run(db.conn))


@cached(
    cache=TTLCache(maxsize=10, ttl=30),
    key=lambda months_without_use, categories: (
        months_without_use,
        frozenset(categories) if categories else (),
    ),
)
def get_unused_desktops(months_without_use=6, categories=[]):
    unused_desktops_query = r.table("domains")
    if categories:
        unused_desktops_query = unused_desktops_query.get_all(
            r.args(categories), index="category"
        ).filter(lambda row: (row["kind"] == "desktop") & (~row["server"]))
    else:
        unused_desktops_query = unused_desktops_query.get_all(
            "desktop", index="kind"
        ).filter(lambda row: ~row["server"])

    unused_desktops_query = (
        unused_desktops_query.merge(
            lambda desktop: {
                "last_accessed": r.branch(
                    r.table("logs_desktops")
                    .get_all(desktop["id"], index="desktop_id")
                    .filter(
                        lambda log: r.expr(
                            [
                                "desktop-owner",
                                "deployment-owner",
                                "desktop-directviewer",
                            ]
                        ).contains(log["starting_by"])
                    )
                    .is_empty(),  # If no logs are found
                    # Fallback to the `accessed` field
                    r.epoch_time(desktop["accessed"]).default(None),
                    # Otherwise, get the most recent `starting_time` from logs
                    r.table("logs_desktops")
                    .get_all(desktop["id"], index="desktop_id")
                    .filter(
                        lambda log: r.expr(
                            [
                                "desktop-owner",
                                "deployment-owner",
                                "desktop-directviewer",
                            ]
                        ).contains(log["starting_by"])
                    )
                    .order_by(r.desc("starting_time"))  # Sort by most recent
                    .nth(0)["starting_time"]
                    .default(
                        r.epoch_time(desktop["accessed"]).default(None)
                    ),  # Fallback to `accessed`
                ),
            }
        )
        .filter(
            # Filter based on `last_accessed` logic
            lambda desktop: desktop["last_accessed"].lt(
                r.now().sub(r.expr(60 * 60 * 24 * 30 * months_without_use))
            )
        )
        .eq_join(
            r.row["create_dict"]["hardware"]["disks"][0]["storage_id"],
            r.table("storage"),
        )
        .without({"right": {"id": True}})
        .zip()
        .merge(
            lambda desktop: {
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
        unuseds = list(unused_desktops_query.run(db.conn))

    total_size = sum([d["size"] for d in unuseds])
    return {"size": total_size, "desktops": unuseds}


def suggested_removals(categories=None, months_without_use=6):
    suggestions = {
        "empty_deployments": get_empty_deployments(categories),
        "unused_desktops": get_unused_desktops(months_without_use, categories),
    }
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


def get_desktops_less_used(
    days_before=30, limit=None, not_in_directory_path=None, status=False
):
    cutoff_date = r.now().sub(r.expr(60 * 60 * 24 * days_before))

    query = r.table("domains")
    if status:
        query = query.get_all(["desktop", status], index="kind_status")
    else:
        query = query.get_all("desktop", index="kind")
    query = (
        query.map(
            lambda desktop: {
                "desktop_id": desktop["id"],
                "desktop_status": desktop["status"],
                "desktop_category": desktop["category"],
                "last_accessed": r.branch(
                    r.table("logs_desktops")
                    .get_all(desktop["id"], index="desktop_id")
                    .filter(
                        lambda log: r.expr(
                            [
                                "desktop-owner",
                                "deployment-owner",
                                "desktop-directviewer",
                            ]
                        ).contains(log["starting_by"])
                    )
                    .is_empty(),  # If no logs are found
                    r.epoch_time(desktop["accessed"]).default(None),  # Use `accessed`
                    r.table("logs_desktops")
                    .get_all(desktop["id"], index="desktop_id")
                    .filter(
                        lambda log: r.expr(
                            [
                                "desktop-owner",
                                "deployment-owner",
                                "desktop-directviewer",
                            ]
                        ).contains(log["starting_by"])
                    )
                    .order_by(r.desc("starting_time"))  # Get the most recent log
                    .nth(0)["starting_time"]
                    .default(
                        r.epoch_time(desktop["accessed"]).default(None)
                    ),  # Fallback to `accessed`
                ),
                "storage_id": desktop["create_dict"]["hardware"]["disks"][0][
                    "storage_id"
                ],
            }
        )
        .filter(
            lambda desktop: (
                (desktop["last_accessed"] == None)
                | (desktop["last_accessed"].lt(cutoff_date))
            )
        )
        .eq_join("storage_id", r.table("storage"))
    )

    if not_in_directory_path:
        query = query.filter(
            lambda join_result: join_result["right"]["directory_path"]
            != not_in_directory_path
        )

    query = query.map(
        lambda join_result: join_result["left"].merge(
            {
                "directory_path": join_result["right"]["directory_path"],
                "storage_path": join_result["right"]["directory_path"]
                + "/"
                + join_result["left"]["storage_id"]
                + "."
                + join_result["right"]["type"],
                "storage_status": join_result["right"]["status"],
                "size": join_result["right"]["qemu-img-info"]["actual-size"].default(0)
                / 1073741824,
            }
        )
    ).order_by(
        "last_accessed"
    )  # Oldest first

    if limit:
        query = query.limit(limit)

    with app.app_context():
        return list(query.run(db.conn))


def get_desktops_recently_used(
    days_before=30, limit=None, not_in_directory_path=None, status=False
):
    cutoff_date = r.now().sub(r.expr(60 * 60 * 24 * days_before))

    query = r.table("domains")
    if status:
        query = query.get_all(["desktop", status], index="kind_status")
    else:
        query = query.get_all("desktop", index="kind")
    query = (
        query.map(
            lambda desktop: {
                "desktop_id": desktop["id"],
                "desktop_status": desktop["status"],
                "desktop_category": desktop["category"],
                "last_accessed": r.branch(
                    r.table("logs_desktops")
                    .get_all(desktop["id"], index="desktop_id")
                    .is_empty(),
                    r.epoch_time(desktop["accessed"]).default(
                        None
                    ),  # Fallback to accessed
                    r.table("logs_desktops")
                    .get_all(desktop["id"], index="desktop_id")
                    .order_by(r.desc("starting_time"))
                    .nth(0)["starting_time"]
                    .default(
                        r.epoch_time(desktop["accessed"]).default(None)
                    ),  # Fallback again
                ),
                "storage_id": desktop["create_dict"]["hardware"]["disks"][0][
                    "storage_id"
                ],
            }
        )
        .filter(
            lambda desktop: (
                (desktop["last_accessed"] != None)
                & (desktop["last_accessed"].ge(cutoff_date))
            )
        )
        .eq_join("storage_id", r.table("storage"))
    )

    if not_in_directory_path:
        query = query.filter(
            lambda join_result: join_result["right"]["directory_path"]
            != not_in_directory_path
        )

    query = query.map(
        lambda join_result: join_result["left"].merge(
            {
                "directory_path": join_result["right"]["directory_path"],
                "storage_path": join_result["right"]["directory_path"]
                + "/"
                + join_result["left"]["storage_id"]
                + "."
                + join_result["right"]["type"],
                "storage_status": join_result["right"]["status"],
                "size": join_result["right"]["qemu-img-info"]["actual-size"].default(0)
                / 1073741824,
            }
        )
    ).order_by(
        r.desc("last_accessed")
    )  # Most recent first

    if limit:
        query = query.limit(limit)

    with app.app_context():
        return list(query.run(db.conn))


def get_desktops_most_used(
    days_before=7, limit=None, not_in_directory_path=None, status=False
):
    """
    Get the most started desktops in the last `days_before` days.

    :param days_before: The number of days to look back
    :param limit: The maximum number of results to return
    :param not_in_directory_path: Skip desktops with a specific directory_path
    :param status: Filter by desktop status
    :return: A list of desktops
    """

    query = (
        r.table("logs_desktops")
        .filter(
            lambda log: log["starting_time"].during(
                r.now().sub(r.expr(60 * 60 * 24 * days_before)),
                r.now(),
            )
        )
        .group("desktop_id")
        .count()
        .ungroup()
        .map(
            lambda group: {
                "desktop_id": group["group"],
                "start_count": group["reduction"],
            }
        )
        .order_by(r.desc("start_count"))
    )

    if status:
        query = (
            query.eq_join("desktop_id", r.table("domains"))
            .filter({"right": {"status": status}})
            .map(
                lambda join_result: {
                    "desktop_id": join_result["left"]["desktop_id"],
                    "start_count": join_result["left"]["start_count"],
                    "desktop_status": join_result["right"]["status"],
                    "desktop_category": join_result["right"]["category"],
                    "storage_id": join_result["right"]["create_dict"]["hardware"][
                        "disks"
                    ][0]["storage_id"],
                }
            )
        )
    else:
        query = query.eq_join("desktop_id", r.table("domains"))

    query = query.eq_join("storage_id", r.table("storage"))

    if not_in_directory_path:
        query = query.filter(
            lambda join_result: join_result["right"]["directory_path"]
            != not_in_directory_path
        )

    query = query.map(
        lambda join_result: {
            "desktop_id": join_result["left"]["desktop_id"],
            "start_count": join_result["left"]["start_count"],
            "desktop_status": join_result["left"]["desktop_status"],
            "storage_id": join_result["left"]["storage_id"],
            "storage_status": join_result["right"]["status"],
            "directory_path": join_result["right"]["directory_path"],
            "storage_path": join_result["right"]["directory_path"]
            + "/"
            + join_result["left"]["storage_id"]
            + "."
            + join_result["right"]["type"],
            "desktop_category": join_result["left"]["desktop_category"],
            "size": join_result["right"]["qemu-img-info"]["actual-size"].default(0)
            / 1073741824,
        }
    )

    if limit:
        query = query.limit(limit)

    with app.app_context():
        results = list(query.run(db.conn))

    return results
