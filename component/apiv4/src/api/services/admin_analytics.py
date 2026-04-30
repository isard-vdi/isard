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

from datetime import datetime

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.error_factory import Error
from rethinkdb import r


class AdminAnalyticsService:
    """Service for analytics: storage usage, resource counts, suggested removals,
    graph configurations, desktop analytics, and echart data."""

    # =========================================================================
    # STORAGE & RESOURCE ANALYTICS
    # =========================================================================

    @staticmethod
    def storage_usage(categories=None):
        storage = {}
        if categories:
            with RethinkSharedConnection._rdb_context():
                storage["media"] = (
                    r.table("media")
                    .get_all(r.args(categories), index="category")
                    .filter(r.row["status"].ne("deleted"))
                    .pluck({"progress": "total_bytes"})
                    .sum(lambda size: size["progress"]["total_bytes"].default(0))
                    .run(RethinkSharedConnection._rdb_connection)
                ) / 10737418240
            with RethinkSharedConnection._rdb_context():
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
                                lambda right: right["qemu-img-info"][
                                    "actual-size"
                                ].default(0)
                            ),
                        }
                    )
                    .sum("storage")
                    / 1073741824
                ).run(RethinkSharedConnection._rdb_connection)
        else:
            with RethinkSharedConnection._rdb_context():
                storage["media"] = (
                    r.table("media")
                    .filter(r.row["status"].ne("deleted"))
                    .pluck({"progress": "total_bytes"})
                    .sum(lambda size: size["progress"]["total_bytes"].default(0))
                    .run(RethinkSharedConnection._rdb_connection)
                ) / 1073741824
            with RethinkSharedConnection._rdb_context():
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
                                lambda right: right["qemu-img-info"][
                                    "actual-size"
                                ].default(0)
                            ),
                        }
                    )
                    .sum("storage")
                    / 1073741824
                ).run(RethinkSharedConnection._rdb_connection)
        return storage

    @staticmethod
    def resource_count(categories=None):
        count = {}
        if categories:
            with RethinkSharedConnection._rdb_context():
                count["desktops"] = (
                    r.table("domains")
                    .get_all(r.args(categories), index="category")
                    .filter({"kind": "desktop"})
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )
            with RethinkSharedConnection._rdb_context():
                count["templates"] = (
                    r.table("domains")
                    .get_all(r.args(categories), index="category")
                    .filter({"kind": "template"})
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )
            with RethinkSharedConnection._rdb_context():
                count["media"] = (
                    r.table("media")
                    .get_all(r.args(categories), index="category")
                    .filter(r.row["status"].ne("deleted"))
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )
            with RethinkSharedConnection._rdb_context():
                count["users"] = (
                    r.table("users")
                    .get_all(r.args(categories), index="category")
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )
            with RethinkSharedConnection._rdb_context():
                count["groups"] = (
                    r.table("groups")
                    .get_all(r.args(categories), index="parent_category")
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )
            with RethinkSharedConnection._rdb_context():
                count["deployments"] = (
                    r.table("deployments")
                    .eq_join("user", r.table("users"))
                    .filter(
                        lambda deployment: r.expr(categories).contains(
                            deployment["right"]["category"]
                        )
                    )
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )
        else:
            with RethinkSharedConnection._rdb_context():
                count["desktops"] = (
                    r.table("domains")
                    .get_all("desktop", index="kind")
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )
            with RethinkSharedConnection._rdb_context():
                count["templates"] = (
                    r.table("domains")
                    .get_all("template", index="kind")
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )
            with RethinkSharedConnection._rdb_context():
                count["media"] = (
                    r.table("media")
                    .filter(r.row["status"].ne("deleted"))
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )
            with RethinkSharedConnection._rdb_context():
                count["users"] = (
                    r.table("users")
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )
            with RethinkSharedConnection._rdb_context():
                count["groups"] = (
                    r.table("groups")
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )
            with RethinkSharedConnection._rdb_context():
                count["deployments"] = (
                    r.table("deployments")
                    .count()
                    .run(RethinkSharedConnection._rdb_connection)
                )
        return count

    @staticmethod
    def suggested_removals(categories=None, months_without_use=6):
        suggestions = {
            "empty_deployments": AdminAnalyticsService._get_empty_deployments(
                categories
            ),
            "unused_desktops": AdminAnalyticsService._get_unused_desktops(
                months_without_use, categories
            ),
        }
        return suggestions

    @staticmethod
    def _get_empty_deployments(categories=None):
        empty_deployments_query = r.table("deployments").eq_join(
            "user", r.table("users")
        )
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
        with RethinkSharedConnection._rdb_context():
            return list(
                empty_deployments_query.run(RethinkSharedConnection._rdb_connection)
            )

    @staticmethod
    def _get_unused_desktops(months_without_use=6, categories=None):
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
                        .is_empty(),
                        r.epoch_time(desktop["accessed"]).default(None),
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
                        .order_by(r.desc("starting_time"))
                        .nth(0)["starting_time"]
                        .default(r.epoch_time(desktop["accessed"]).default(None)),
                    ),
                }
            )
            .filter(
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
                    "size": desktop["qemu-img-info"]["actual-size"].default(0)
                    / 1073741824,
                }
            )
            .pluck(
                "id",
                "name",
                "category_name",
                "group_name",
                "username",
                "size",
            )
        )
        with RethinkSharedConnection._rdb_context():
            unuseds = list(
                unused_desktops_query.run(RethinkSharedConnection._rdb_connection)
            )
        total_size = sum([d["size"] for d in unuseds])
        return {"size": total_size, "desktops": unuseds}

    # =========================================================================
    # GRAPH CONFIGURATION
    # =========================================================================

    @staticmethod
    def get_usage_graphs_conf():
        with RethinkSharedConnection._rdb_context():
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
                .run(RethinkSharedConnection._rdb_connection)
            )

    @staticmethod
    def get_usage_graph_conf(graph_conf_id):
        with RethinkSharedConnection._rdb_context():
            result = (
                r.table("analytics")
                .get(graph_conf_id)
                .run(RethinkSharedConnection._rdb_connection)
            )
        if not result:
            raise Error("not_found", "Graph configuration not found")
        return result

    @staticmethod
    def add_usage_graph_conf(data):
        with RethinkSharedConnection._rdb_context():
            r.table("analytics").insert(data).run(
                RethinkSharedConnection._rdb_connection
            )

    @staticmethod
    def update_usage_graph_conf(graph_conf_id, data):
        with RethinkSharedConnection._rdb_context():
            r.table("analytics").get(graph_conf_id).update(data).run(
                RethinkSharedConnection._rdb_connection
            )

    @staticmethod
    def delete_usage_graph_conf(graph_conf_id):
        with RethinkSharedConnection._rdb_context():
            r.table("analytics").get(graph_conf_id).delete().run(
                RethinkSharedConnection._rdb_connection
            )

    # =========================================================================
    # DESKTOP ANALYTICS
    # =========================================================================

    @staticmethod
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
                        .is_empty(),
                        r.epoch_time(desktop["accessed"]).default(None),
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
                        .order_by(r.desc("starting_time"))
                        .nth(0)["starting_time"]
                        .default(r.epoch_time(desktop["accessed"]).default(None)),
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
                .match(f"^{not_in_directory_path}")
                .not_()
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
                    "size": join_result["right"]["qemu-img-info"][
                        "actual-size"
                    ].default(0)
                    / 1073741824,
                }
            )
        ).order_by("last_accessed")

        if limit:
            query = query.limit(limit)

        with RethinkSharedConnection._rdb_context():
            return list(query.run(RethinkSharedConnection._rdb_connection))

    @staticmethod
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
                        r.epoch_time(desktop["accessed"]).default(None),
                        r.table("logs_desktops")
                        .get_all(desktop["id"], index="desktop_id")
                        .order_by(r.desc("starting_time"))
                        .nth(0)["starting_time"]
                        .default(r.epoch_time(desktop["accessed"]).default(None)),
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
                .match(f"^{not_in_directory_path}")
                .not_()
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
                    "size": join_result["right"]["qemu-img-info"][
                        "actual-size"
                    ].default(0)
                    / 1073741824,
                }
            )
        ).order_by(r.desc("last_accessed"))

        if limit:
            query = query.limit(limit)

        with RethinkSharedConnection._rdb_context():
            return list(query.run(RethinkSharedConnection._rdb_connection))

    @staticmethod
    def get_desktops_most_used(
        days_before=7, limit=None, not_in_directory_path=None, status=False
    ):
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
                .match(f"^{not_in_directory_path}")
                .not_()
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

        with RethinkSharedConnection._rdb_context():
            return list(query.run(RethinkSharedConnection._rdb_connection))

    # =========================================================================
    # ECHART DATA
    # =========================================================================

    @staticmethod
    def get_daily_items(table, date_field):
        with RethinkSharedConnection._rdb_context():
            data = (
                r.table(table)
                .group(
                    lambda match: [
                        match[date_field].year(),
                        match[date_field].month(),
                        match[date_field].day(),
                    ]
                )
                .count()
                .run(RethinkSharedConnection._rdb_connection)
            )
        return {
            "x": [datetime(*k).isoformat() for k in data.keys()],
            "series": {date_field: [v for v in data.values()]},
        }

    @staticmethod
    def get_grouped_data(table, field):
        # Check if field is an index on the table
        with RethinkSharedConnection._rdb_context():
            indexes = list(
                r.table(table).index_list().run(RethinkSharedConnection._rdb_connection)
            )
        query = r.table(table)
        query = query.group(index=field) if field in indexes else query.group(field)
        with RethinkSharedConnection._rdb_context():
            data = query.count().run(RethinkSharedConnection._rdb_connection)
        return [{"value": v, "name": k} for k, v in data.items() if k is not None]

    @staticmethod
    def get_grouped_unique_data(table, field, unique_field):
        with RethinkSharedConnection._rdb_context():
            indexes = list(
                r.table(table).index_list().run(RethinkSharedConnection._rdb_connection)
            )
        query = r.table(table)
        query = query.group(index=field) if field in indexes else query.group(field)
        query = query.map(lambda group: group[unique_field]).distinct().count()
        with RethinkSharedConnection._rdb_context():
            data = query.run(RethinkSharedConnection._rdb_connection)
        return [{"value": v, "name": k} for k, v in data.items() if k is not None]

    @staticmethod
    def get_nested_array_grouped_data(table, array_field, field):
        with RethinkSharedConnection._rdb_context():
            data = (
                r.table(table)
                .concat_map(
                    lambda doc: doc[array_field].map(
                        lambda array: {
                            "desktop_id": doc["desktop_id"],
                            field: array[field],
                        }
                    )
                )
                .group(field)
                .count()
                .run(RethinkSharedConnection._rdb_connection)
            )
        return [{"value": v, "name": k} for k, v in data.items() if k is not None]
