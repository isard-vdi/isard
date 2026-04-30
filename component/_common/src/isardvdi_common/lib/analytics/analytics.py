#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Layer-2 helpers for the admin analytics dashboard.

Backs ``/api/v4/admin/analytics/*`` with reads over the live tables
(``domains`` / ``storage`` / ``media`` / ``users`` / ``groups`` /
``deployments`` / ``logs_desktops``) plus CRUD on the ``analytics``
table (graph configurations) and a handful of generic eChart
aggregators (daily counts, grouped counts, etc.).

Heavy joins-and-merges live here intentionally: the rdb engine can
plan them server-side, while pulling the rows to apiv4 and joining in
Python would scale badly on big sites.
"""

from datetime import datetime

from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from rethinkdb import r


class AnalyticsProcessed(RethinkSharedConnection):
    """Layer-2 entry point for admin analytics."""

    # =====================================================================
    # STORAGE & RESOURCE ANALYTICS
    # =====================================================================

    @classmethod
    def storage_usage(cls, categories: list[str] | None = None) -> dict:
        """Return media + per-user-storage usage in GiB (or in `categories`).

        Two pulls:

        * ``media`` — sum of every non-deleted media's
          ``progress.total_bytes``;
        * ``domains`` — sum of every user's ready-storage's
          ``qemu-img-info.actual-size``.

        Both are normalised to GiB. When ``categories`` is provided the
        first uses /10 GiB scaling per the legacy contract; we preserve
        that exactly.
        """
        storage: dict = {}
        if categories:
            with cls._rdb_context():
                storage["media"] = (
                    r.table("media")
                    .get_all(r.args(categories), index="category")
                    .filter(r.row["status"].ne("deleted"))
                    .pluck({"progress": "total_bytes"})
                    .sum(lambda size: size["progress"]["total_bytes"].default(0))
                    .run(cls._rdb_connection)
                ) / 10737418240
            with cls._rdb_context():
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
                ).run(cls._rdb_connection)
        else:
            with cls._rdb_context():
                storage["media"] = (
                    r.table("media")
                    .filter(r.row["status"].ne("deleted"))
                    .pluck({"progress": "total_bytes"})
                    .sum(lambda size: size["progress"]["total_bytes"].default(0))
                    .run(cls._rdb_connection)
                ) / 1073741824
            with cls._rdb_context():
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
                ).run(cls._rdb_connection)
        return storage

    @classmethod
    def resource_count(cls, categories: list[str] | None = None) -> dict:
        """Return per-resource counts (desktops, templates, media, users, ...).

        When ``categories`` is given each table is scoped to that list.
        Six rdb round-trips total (one per resource); the admin
        dashboard refreshes infrequently enough that batching them is
        not worth the merge complexity.
        """
        count: dict = {}
        if categories:
            with cls._rdb_context():
                count["desktops"] = (
                    r.table("domains")
                    .get_all(r.args(categories), index="category")
                    .filter({"kind": "desktop"})
                    .count()
                    .run(cls._rdb_connection)
                )
            with cls._rdb_context():
                count["templates"] = (
                    r.table("domains")
                    .get_all(r.args(categories), index="category")
                    .filter({"kind": "template"})
                    .count()
                    .run(cls._rdb_connection)
                )
            with cls._rdb_context():
                count["media"] = (
                    r.table("media")
                    .get_all(r.args(categories), index="category")
                    .filter(r.row["status"].ne("deleted"))
                    .count()
                    .run(cls._rdb_connection)
                )
            with cls._rdb_context():
                count["users"] = (
                    r.table("users")
                    .get_all(r.args(categories), index="category")
                    .count()
                    .run(cls._rdb_connection)
                )
            with cls._rdb_context():
                count["groups"] = (
                    r.table("groups")
                    .get_all(r.args(categories), index="parent_category")
                    .count()
                    .run(cls._rdb_connection)
                )
            with cls._rdb_context():
                count["deployments"] = (
                    r.table("deployments")
                    .eq_join("user", r.table("users"))
                    .filter(
                        lambda deployment: r.expr(categories).contains(
                            deployment["right"]["category"]
                        )
                    )
                    .count()
                    .run(cls._rdb_connection)
                )
        else:
            with cls._rdb_context():
                count["desktops"] = (
                    r.table("domains")
                    .get_all("desktop", index="kind")
                    .count()
                    .run(cls._rdb_connection)
                )
            with cls._rdb_context():
                count["templates"] = (
                    r.table("domains")
                    .get_all("template", index="kind")
                    .count()
                    .run(cls._rdb_connection)
                )
            with cls._rdb_context():
                count["media"] = (
                    r.table("media")
                    .filter(r.row["status"].ne("deleted"))
                    .count()
                    .run(cls._rdb_connection)
                )
            with cls._rdb_context():
                count["users"] = r.table("users").count().run(cls._rdb_connection)
            with cls._rdb_context():
                count["groups"] = r.table("groups").count().run(cls._rdb_connection)
            with cls._rdb_context():
                count["deployments"] = (
                    r.table("deployments").count().run(cls._rdb_connection)
                )
        return count

    @classmethod
    def suggested_removals(
        cls,
        categories: list[str] | None = None,
        months_without_use: int = 6,
    ) -> dict:
        """Return both empty-deployments and unused-desktops suggestions."""
        return {
            "empty_deployments": cls.get_empty_deployments(categories),
            "unused_desktops": cls.get_unused_desktops(months_without_use, categories),
        }

    @classmethod
    def get_empty_deployments(cls, categories: list[str] | None = None) -> list[dict]:
        """Return deployments with zero domains attached."""
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
        with cls._rdb_context():
            return list(empty_deployments_query.run(cls._rdb_connection))

    @classmethod
    def get_unused_desktops(
        cls,
        months_without_use: int = 6,
        categories: list[str] | None = None,
    ) -> dict:
        """Return desktops not accessed for ``months_without_use`` months.

        Cross-joined with their backing storage so the admin can size up
        a bulk-cleanup. Result carries ``size`` in GiB and a running
        ``size`` total alongside the per-row list.
        """
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
        with cls._rdb_context():
            unuseds = list(unused_desktops_query.run(cls._rdb_connection))
        total_size = sum([d["size"] for d in unuseds])
        return {"size": total_size, "desktops": unuseds}

    # =====================================================================
    # GRAPH CONFIGURATION (table ``analytics``)
    # =====================================================================

    @classmethod
    def list_graph_configs(cls) -> list[dict]:
        """Return every graph config row with its grouping name resolved."""
        with cls._rdb_context():
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
                .run(cls._rdb_connection)
            )

    @classmethod
    def get_graph_config(cls, graph_conf_id: str) -> dict:
        """Return one graph config; raises ``not_found`` when missing."""
        from isardvdi_common.helpers.error_factory import Error

        with cls._rdb_context():
            result = r.table("analytics").get(graph_conf_id).run(cls._rdb_connection)
        if not result:
            raise Error("not_found", "Graph configuration not found")
        return result

    @classmethod
    def create_graph_config(cls, data: dict) -> None:
        """Insert a new graph config row."""
        with cls._rdb_context():
            r.table("analytics").insert(data).run(cls._rdb_connection)

    @classmethod
    def update_graph_config(cls, graph_conf_id: str, data: dict) -> None:
        """Update a graph config row by id."""
        with cls._rdb_context():
            r.table("analytics").get(graph_conf_id).update(data).run(
                cls._rdb_connection
            )

    @classmethod
    def delete_graph_config(cls, graph_conf_id: str) -> None:
        """Delete a graph config row by id."""
        with cls._rdb_context():
            r.table("analytics").get(graph_conf_id).delete().run(cls._rdb_connection)

    # =====================================================================
    # DESKTOP ANALYTICS
    # =====================================================================

    @classmethod
    def get_desktops_less_used(
        cls,
        days_before: int = 30,
        limit: int | None = None,
        not_in_directory_path: str | None = None,
        status: str | bool = False,
    ) -> list[dict]:
        """Return desktops that haven't been accessed in ``days_before`` days."""
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
                    (desktop["last_accessed"] == None)  # noqa: E711
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

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def get_desktops_recently_used(
        cls,
        days_before: int = 30,
        limit: int | None = None,
        not_in_directory_path: str | None = None,
        status: str | bool = False,
    ) -> list[dict]:
        """Return desktops accessed within the last ``days_before`` days."""
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
                    (desktop["last_accessed"] != None)  # noqa: E711
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

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def get_desktops_most_used(
        cls,
        days_before: int = 7,
        limit: int | None = None,
        not_in_directory_path: str | None = None,
        status: str | bool = False,
    ) -> list[dict]:
        """Return desktops with the most ``logs_desktops`` start events."""
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

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    # =====================================================================
    # ECHART DATA
    # =====================================================================

    @classmethod
    def get_daily_items(cls, table: str, date_field: str) -> dict:
        """Return ``(year, month, day)``-bucketed counts for ``table[date_field]``.

        Output shape matches the eChart contract: ``{x: [iso-dates], series:
        {<date_field>: [counts]}}``.
        """
        with cls._rdb_context():
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
                .run(cls._rdb_connection)
            )
        return {
            "x": [datetime(*k).isoformat() for k in data.keys()],
            "series": {date_field: [v for v in data.values()]},
        }

    @classmethod
    def get_grouped_data(cls, table: str, field: str) -> list[dict]:
        """Return ``[{value, name}]`` count buckets keyed by ``field``.

        Auto-detects whether ``field`` is a secondary index on ``table``
        and uses ``group(index=...)`` when so (faster).
        """
        with cls._rdb_context():
            indexes = list(r.table(table).index_list().run(cls._rdb_connection))
        query = r.table(table)
        query = query.group(index=field) if field in indexes else query.group(field)
        with cls._rdb_context():
            data = query.count().run(cls._rdb_connection)
        return [{"value": v, "name": k} for k, v in data.items() if k is not None]

    @classmethod
    def get_grouped_unique_data(
        cls, table: str, field: str, unique_field: str
    ) -> list[dict]:
        """Return ``[{value, name}]`` count of distinct ``unique_field`` per group."""
        with cls._rdb_context():
            indexes = list(r.table(table).index_list().run(cls._rdb_connection))
        query = r.table(table)
        query = query.group(index=field) if field in indexes else query.group(field)
        query = query.map(lambda group: group[unique_field]).distinct().count()
        with cls._rdb_context():
            data = query.run(cls._rdb_connection)
        return [{"value": v, "name": k} for k, v in data.items() if k is not None]

    @classmethod
    def get_nested_array_grouped_data(
        cls, table: str, array_field: str, field: str
    ) -> list[dict]:
        """Return ``[{value, name}]`` count of ``array_field[*][field]`` values."""
        with cls._rdb_context():
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
                .run(cls._rdb_connection)
            )
        return [{"value": v, "name": k} for k, v in data.items() if k is not None]
