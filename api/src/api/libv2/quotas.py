#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log
import traceback

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from isardvdi_common.api_exceptions import Error
from rethinkdb.errors import ReqlNonExistenceError

from .api_allowed import ApiAllowed
from .quotas_process import QuotasProcess

allowed = ApiAllowed()

qp = QuotasProcess()


class Quotas:
    def __init__(self):
        None

    def get_applied_quota(self, user_id):
        with app.app_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck("id", "name", "category", "group", "quota")
                .run(db.conn)
            )
        with app.app_context():
            group = (
                r.table("groups").get(user["group"]).pluck("name", "quota").run(db.conn)
            )
        with app.app_context():
            category = (
                r.table("categories")
                .get(user["category"])
                .pluck("name", "quota")
                .run(db.conn)
            )

        if user["quota"]:
            return {
                "quota": user["quota"],
                "restriction_applied": "user_quota",
            }
        elif group["quota"]:
            return {
                "quota": group["quota"],
                "restriction_applied": "group_quota",
            }
        elif category["quota"]:
            return {
                "quota": category["quota"],
                "restriction_applied": "category_quota",
            }
        else:
            return {"quota": False, "restriction_applied": "user_quota"}

    # Get in user["quota"] the applied quota, either user, group or category
    # TODO: Use get_applied_quota function
    def Get(self, user_id, started_info=True):
        with app.app_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck("id", "name", "category", "group", "quota")
                .run(db.conn)
            )
        with app.app_context():
            group = (
                r.table("groups").get(user["group"]).pluck("name", "quota").run(db.conn)
            )
        with app.app_context():
            category = (
                r.table("categories")
                .get(user["category"])
                .pluck("name", "quota")
                .run(db.conn)
            )

        # Used
        with app.app_context():
            user_desktops = (
                r.table("domains")
                .get_all(
                    ["desktop", user_id, False],
                    index="kind_user_tag",
                )
                .filter({"persistent": True})
                .count()
                .run(db.conn)
            )
        with app.app_context():
            user_volatile = (
                r.table("domains")
                .get_all(["desktop", user_id], index="kind_user")
                .filter({"persistent": False})
                .count()
                .run(db.conn)
            )
        with app.app_context():
            user_templates = (
                r.table("domains")
                .get_all(["template", user_id, False], index="kind_user_tag")
                .filter({"enabled": True})
                .count()
                .run(db.conn)
            )
        with app.app_context():
            user_media = (
                r.table("media")
                .get_all(["Downloaded", user_id], index="status_user")
                .count()
                .run(db.conn)
            )
        with app.app_context():
            user_deployments = (
                r.table("deployments")
                .get_all(user_id, index="user")
                .count()
                .run(db.conn)
            )
        user_deployment_desktops = 0

        with app.app_context():
            user_total_storage_size = (
                (
                    r.table("storage")
                    .get_all([user_id, "ready"], index="user_status")
                    .sum(lambda size: size["qemu-img-info"]["actual-size"].default(0))
                    .run(db.conn)
                )
                + (
                    r.table("storage")
                    .get_all([user_id, "recycled"], index="user_status")
                    .sum(lambda size: size["qemu-img-info"]["actual-size"].default(0))
                    .run(db.conn)
                )
            ) / 1073741824

        with app.app_context():
            user_total_media_size = (
                r.table("media")
                .get_all(["Downloaded", user_id], index="status_user")
                .sum(lambda size: size["progress"]["total_bytes"].default(0))
                .run(db.conn)
            ) / 1073741824

        user_total_size = user_total_storage_size + user_total_media_size

        used = {
            "desktops": user_desktops,
            "volatile": user_volatile,
            "templates": user_templates,
            "isos": user_media,
            "total_size": user_total_size,
            "media_size": user_total_media_size,
            "storage_size": user_total_storage_size,
            "deployments_total": user_deployments,
            "deployment_desktops": user_deployment_desktops,
            "started_deployment_desktops": self.get_started_deployment_desktops(
                user_id
            ),
        }

        if started_info:
            started_desktops = self.get_started_desktops(
                user_id, "kind_user", owner_only=True
            )
            used["running"] = started_desktops["count"]
            used["memory"] = started_desktops["memory"]
            used["vcpus"] = started_desktops["vcpus"]

        if user["quota"]:
            return {
                "quota": user["quota"],
                "used": used,
                "restriction_applied": "user_quota",
            }
        elif group["quota"]:
            return {
                "quota": group["quota"],
                "used": used,
                "restriction_applied": "group_quota",
            }
        elif category["quota"]:
            return {
                "quota": category["quota"],
                "used": used,
                "restriction_applied": "category_quota",
            }
        else:
            return {"quota": False, "used": used, "restriction_applied": "user_quota"}

    def GetUserQuota(self, user_id):
        return qp.get_user(user_id)

    """ Used to edit category/group/user in admin """

    def GetCategoryQuota(self, category_id):
        with app.app_context():
            category = (
                r.table("categories")
                .get(category_id)
                .pluck("limits", "quota")
                .run(db.conn)
            )
        return {"quota": category["quota"], "limits": category["limits"]}

    def GetGroupQuota(self, group_id):
        ### Limits for group will be at least limits for its category
        with app.app_context():
            group = (
                r.table("groups")
                .get(group_id)
                .pluck("parent_category", "limits", "quota")
                .run(db.conn)
            )
        limits = group["limits"]
        if limits == False:
            with app.app_context():
                limits = (
                    r.table("categories")
                    .get(group["parent_category"])
                    .pluck("limits")
                    .run(db.conn)["limits"]
                )
        return {
            "quota": group["quota"],
            "limits": limits,  ##Category limits as maximum
            "grouplimits": group["limits"],
        }

    def UserCreate(self, category_id, group_id):
        qp.check_new_autoregistered_user(category_id, group_id)

    def desktop_create(self, user_id, quantity=1):
        try:
            with app.app_context():
                user = (
                    r.table("users")
                    .get(user_id)
                    .merge(
                        lambda d: {
                            "category_name": r.table("categories").get(d["category"])[
                                "name"
                            ],
                            "group_name": r.table("groups").get(d["group"])["name"],
                            "role_name": r.table("roles").get(d["role"])["name"],
                        }
                    )
                    .pluck(
                        "id",
                        "name",
                        "category",
                        "group",
                        "quota",
                        "category_name",
                        "group_name",
                        "role_name",
                    )
                    .run(db.conn)
                )
        except:
            raise Error("not_found", "User not found")
        with app.app_context():
            group_quantity = (
                r.table("domains")
                .get_all(["desktop", user["group"]], index="kind_group")
                .filter({"persistent": True})
                .count()
                .run(db.conn)
            )
        with app.app_context():
            category_quantity = (
                r.table("domains")
                .get_all(["desktop", user["category"]], index="kind_category")
                .filter({"persistent": True})
                .count()
                .run(db.conn)
            )
        quota_error = {
            "error_description": user["name"]
            + " quota exceeded for creating new desktop",
            "error_description_code": "desktop_new_user_quota_exceeded",
        }
        limits_error = {
            "group": {
                "error_description": user["group_name"]
                + " group limits exceeded for creating new desktop",
                "error_description_code": "desktop_new_group_limit_exceeded",
            },
            "category": {
                "error_description": user["name"]
                + " category limits exceeded for creating new desktop",
                "error_description_code": "desktop_new_category_limit_exceeded",
            },
        }
        self.check_field_quotas_and_limits(
            user,
            "desktops",
            quantity,
            quota_error,
            group_quantity,
            category_quantity,
            limits_error,
        )

    def volatile_create(self, user_id, quantity=1):
        try:
            with app.app_context():
                user = (
                    r.table("users")
                    .get(user_id)
                    .merge(
                        lambda d: {
                            "category_name": r.table("categories").get(d["category"])[
                                "name"
                            ],
                            "group_name": r.table("groups").get(d["group"])["name"],
                            "role_name": r.table("roles").get(d["role"])["name"],
                        }
                    )
                    .pluck(
                        "id",
                        "name",
                        "category",
                        "group",
                        "quota",
                        "category_name",
                        "group_name",
                        "role_name",
                    )
                    .run(db.conn)
                )
        except:
            raise Error("not_found", "User not found")
        with app.app_context():
            group_quantity = (
                r.table("domains")
                .get_all(["desktop", user["group"]], index="kind_group")
                .filter({"persistent": False})
                .count()
                .run(db.conn)
            )
        with app.app_context():
            category_quantity = (
                r.table("domains")
                .get_all(["desktop", user["category"]], index="kind_category")
                .filter({"persistent": False})
                .count()
                .run(db.conn)
            )
        quota_error = {
            "error_description": user["name"]
            + " quota exceeded for creating new non persistent desktop",
            "error_description_code": "desktop_new_user_quota_exceeded",
        }
        limits_error = {
            "group": {
                "error_description": user["group_name"]
                + " group limits exceeded for creating new non persistent desktop",
                "error_description_code": "desktop_new_group_limit_exceeded",
            },
            "category": {
                "error_description": user["name"]
                + " category limits exceeded for creating new non persistent desktop",
                "error_description_code": "desktop_new_category_limit_exceeded",
            },
        }
        self.check_field_quotas_and_limits(
            user,
            "volatile",
            quantity,
            quota_error,
            group_quantity,
            category_quantity,
            limits_error,
        )

    def template_create(self, user_id, quantity=1):
        try:
            with app.app_context():
                user = (
                    r.table("users")
                    .get(user_id)
                    .merge(
                        lambda d: {
                            "category_name": r.table("categories").get(d["category"])[
                                "name"
                            ],
                            "group_name": r.table("groups").get(d["group"])["name"],
                            "role_name": r.table("roles").get(d["role"])["name"],
                        }
                    )
                    .pluck(
                        "id",
                        "name",
                        "category",
                        "group",
                        "quota",
                        "category_name",
                        "group_name",
                        "role_name",
                    )
                    .run(db.conn)
                )
        except:
            raise Error("not_found", "User not found")
        with app.app_context():
            group_quantity = (
                r.table("domains")
                .get_all(["template", user["group"]], index="kind_group")
                .count()
                .run(db.conn)
            )
        with app.app_context():
            category_quantity = (
                r.table("domains")
                .get_all(["template", user["category"]], index="kind_category")
                .count()
                .run(db.conn)
            )
        quota_error = {
            "error_description": user["name"]
            + " quota exceeded for creating new template",
            "error_description_code": "template_new_user_quota_exceeded",
        }
        limits_error = {
            "group": {
                "error_description": user["group_name"]
                + " group limits exceeded for creating new template",
                "error_description_code": "template_new_group_limit_exceeded",
            },
            "category": {
                "error_description": user["name"]
                + " category limits exceeded for creating new template",
                "error_description_code": "template_new_category_limit_exceeded",
            },
        }
        self.check_field_quotas_and_limits(
            user,
            "templates",
            quantity,
            quota_error,
            group_quantity,
            category_quantity,
            limits_error,
        )

    def media_create(self, user_id, media_size=False, quantity=1):
        try:
            with app.app_context():
                user = (
                    r.table("users")
                    .get(user_id)
                    .merge(
                        lambda d: {
                            "category_name": r.table("categories").get(d["category"])[
                                "name"
                            ],
                            "group_name": r.table("groups").get(d["group"])["name"],
                            "role_name": r.table("roles").get(d["role"])["name"],
                        }
                    )
                    .pluck(
                        "id",
                        "name",
                        "category",
                        "group",
                        "quota",
                        "category_name",
                        "group_name",
                        "role_name",
                    )
                    .run(db.conn)
                )
        except:
            raise Error("not_found", "User not found")

        with app.app_context():
            group_quantity = (
                r.table("media")
                .get_all(user["group"], index="group")
                .count()
                .run(db.conn)
            )

        with app.app_context():
            category_quantity = (
                r.table("media")
                .get_all(user["category"], index="category")
                .count()
                .run(db.conn)
            )
        quota_error = {
            "error_description": user["name"]
            + " quota exceeded for creating new media",
            "error_description_code": "media_new_user_quota_exceeded",
        }
        limits_error = {
            "group": {
                "error_description": user["group_name"]
                + " group limits exceeded for creating new media",
                "error_description_code": "media_new_group_limit_exceeded",
            },
            "category": {
                "error_description": user["name"]
                + " category limits exceeded for creating new media",
                "error_description_code": "media_new_category_limit_exceeded",
            },
        }
        self.check_field_quotas_and_limits(
            user,
            "isos",
            quantity,
            quota_error,
            group_quantity,
            category_quantity,
            limits_error,
        )

        # Check media size restrictions
        if media_size:
            # Get the group used disk size in GB
            with app.app_context():
                group_total_size = (
                    r.table("users")
                    .get_all(user["group"], index="group")
                    .eq_join(
                        [r.row["id"], "ready"], r.table("storage"), index="user_status"
                    )
                    .sum(
                        lambda right: right["right"]["qemu-img-info"][
                            "actual-size"
                        ].default(0)
                    )
                    .run(db.conn)
                ) / 1073741824
            # Get the category used disk size in GB
            with app.app_context():
                category_total_size = (
                    r.table("users")
                    .get_all(user["category"], index="category")
                    .eq_join(
                        [r.row["id"], "ready"], r.table("storage"), index="user_status"
                    )
                    .sum(
                        lambda right: right["right"]["qemu-img-info"][
                            "actual-size"
                        ].default(0)
                    )
                    .run(db.conn)
                ) / 1073741824
            quota_error = {
                "error_description": user["name"]
                + " disk size quota exceeded for creating new media",
                "error_description_code": "total_size_quota_exceeded",
            }
            limits_error = {
                "group": {
                    "error_description": user["group_name"]
                    + " groups disk size limits exceeded for creating new media",
                    "error_description_code": "group_total_size_limit_exceeded",
                },
                "category": {
                    "error_description": user["name"]
                    + " category disk size limits exceeded for creating new media",
                    "error_description_code": "category_total_size_limit_exceeded",
                },
            }
            self.check_field_quotas_and_limits(
                user,
                "total_size",
                media_size / 1073741824,  # Parse to GB
                quota_error,
                group_total_size,
                category_total_size,
                limits_error,
            )

    def check_field_quotas(self, user, quota_key, quantity, quota_error):
        # We get the user applied quota and currently used info to check the quota
        user_quota_data = self.Get(user_id=user["id"], started_info=False)
        if user_quota_data["quota"]:
            user_quota_data["used"][quota_key] = (
                user_quota_data["used"][quota_key] + quantity
            )  # Sum to field to check if creating it would exceed the quota
            self.check_quota(user_quota_data, quota_key, quota_error)

    def check_field_limits(
        self,
        user,
        quota_key,
        quantity,
        group_quantity,
        category_quantity,
        limits_error,
    ):
        try:
            with app.app_context():
                group = (
                    r.table("groups")
                    .get(user["group"])
                    .pluck("name", "quota", "limits")
                    .run(db.conn)
                )
        except:
            raise Error("not_found", "Group not found")

        if group["limits"]:
            self.check_limits(
                item=group,
                quota_key=quota_key,
                quantity=group_quantity + quantity,
                limits_error=limits_error["group"],
            )

        try:
            with app.app_context():
                category = (
                    r.table("categories")
                    .get(user["category"])
                    .pluck("name", "quota", "limits")
                    .run(db.conn)
                )
        except:
            raise Error("not_found", "Category not found")

        if category["limits"]:
            self.check_limits(
                item=category,
                quota_key=quota_key,
                quantity=category_quantity + quantity,
                limits_error=limits_error["category"],
            )

    def check_field_quotas_and_limits(
        self,
        user,
        quota_key,
        quantity,
        quota_error,
        group_quantity,
        category_quantity,
        limits_error,
        check_quota=True,
        check_limits=True,
    ):
        if check_quota:
            self.check_field_quotas(user, quota_key, quantity, quota_error)

        if check_limits:
            self.check_field_limits(
                user,
                quota_key,
                quantity,
                group_quantity,
                category_quantity,
                limits_error,
            )

    def check_quota(self, user, quota_key, quota_error):
        if user["used"][quota_key] > user["quota"][quota_key]:
            raise Error(
                "precondition_required",
                quota_error["error_description"],
                traceback.format_exc(),
                description_code=quota_error["error_description_code"],
            )

    def check_limits(self, item, quota_key, quantity, limits_error):
        if item["limits"] and quantity > item["limits"][quota_key]:
            raise Error(
                "precondition_required",
                limits_error["error_description"],
                traceback.format_exc(),
                data=quantity,
                description_code=limits_error["error_description_code"],
            )

    def get_started_deployment_desktops(self, user_id):
        # Status that are considered in the running quota
        started_status = [
            "Started",
            "Starting",
            "StartingPaused",
            "CreatingAndStarting",
            "Shutting-down",
        ]

        started_deployment_desktops = 0

        try:
            with app.app_context():
                started_deployment_desktops += (
                    r.table("domains")
                    .get_all(
                        r.args(
                            list(
                                r.table("deployments")
                                .get_all(user_id, index="user")
                                .pluck("id")["id"]
                                .run(db.conn)
                            )
                        ),
                        index="tag",
                    )
                    .filter(
                        lambda desktop: r.expr(started_status).contains(
                            desktop["status"]
                        )
                    )
                    .eq_join("start_logs_id", r.table("logs_desktops"))
                    .pluck({"right": ["starting_by"]}, "left")
                    .zip()
                    .filter(
                        lambda desktop: desktop.get_field("starting_by").eq(
                            "deployment-owner"
                        )
                    )
                    .count()
                    .run(db.conn)
                )
        except ReqlNonExistenceError:
            pass

        try:
            with app.app_context():
                started_deployment_desktops += (
                    r.table("domains")
                    .get_all(
                        r.args(
                            list(
                                r.table("deployments")
                                .get_all(user_id, index="co_owners")
                                .pluck("id")["id"]
                                .run(db.conn)
                            )
                        ),
                        index="tag",
                    )
                    .filter(
                        lambda desktop: r.expr(started_status).contains(
                            desktop["status"]
                        )
                    )
                    .eq_join("start_logs_id", r.table("logs_desktops"))
                    .pluck({"right": ["starting_by"]}, "left")
                    .zip()
                    .filter(
                        lambda desktop: desktop.get_field("starting_by").eq(
                            "deployment-co-owner"
                        )
                    )
                    .count()
                    .run(db.conn)
                )
        except ReqlNonExistenceError:
            pass

        return started_deployment_desktops

    def get_started_desktops(self, query_id, query_index, owner_only=False):
        # Status that are considered in the running quota
        started_status = [
            "Started",
            "Starting",
            "StartingPaused",
            "CreatingAndStarting",
            "Shutting-down",
        ]

        started_desktops = {
            "count": 0,
            "vcpus": 0,
            "memory": 0,
        }

        try:
            with app.app_context():
                started_desktops = (
                    r.table("domains")
                    .get_all(
                        [
                            "desktop",
                            query_id,
                        ],
                        index=query_index,
                    )
                    .filter(
                        lambda desktop: r.expr(started_status).contains(
                            desktop["status"]
                        )
                    )
                    .eq_join("start_logs_id", r.table("logs_desktops"))
                    .pluck({"right": ["starting_by"]}, "left")
                    .zip()
                    .filter(
                        lambda desktop: (
                            desktop.get_field("starting_by").eq("desktop-owner")
                            if owner_only
                            else True
                        )
                    )
                    .map(
                        lambda domain: {
                            "count": 1,
                            "memory": domain["create_dict"]["hardware"]["memory"],
                            "vcpus": domain["create_dict"]["hardware"]["vcpus"],
                        }
                    )
                    .reduce(
                        lambda left, right: {
                            "count": left["count"] + right["count"],
                            "vcpus": left["vcpus"].add(right["vcpus"]),
                            "memory": left["memory"].add(right["memory"]),
                        }
                    )
                    .run(db.conn)
                )
        except ReqlNonExistenceError:
            pass

        started_desktops["memory"] = started_desktops["memory"] / 1048576

        return started_desktops

    def desktop_start(self, user_id, desktop_id):
        with app.app_context():
            desktop = r.table("domains").get(desktop_id).run(db.conn)
        if not desktop:
            raise Error("not_found", "Desktop not found")
        try:
            with app.app_context():
                user = (
                    r.table("users")
                    .get(user_id)
                    .merge(
                        lambda d: {
                            "category_name": r.table("categories").get(d["category"])[
                                "name"
                            ],
                            "group_name": r.table("groups").get(d["group"])["name"],
                            "role_name": r.table("roles").get(d["role"])["name"],
                        }
                    )
                    .pluck(
                        "id",
                        "name",
                        "category",
                        "group",
                        "role",
                        "quota",
                        "category_name",
                        "group_name",
                        "role_name",
                    )
                    .run(db.conn)
                )
            if user["role"] == "admin":
                return desktop
        except:
            raise Error("not_found", "User not found")

        # We get the user applied quota (either user, group or category quota) and currently used info to check the quota
        user_quota_data = self.Get(user_id=user["id"], started_info=True)
        if user_quota_data["quota"]:
            # Add the desktop that would be started to check if starting it would exceed the quota
            user_quota_data["used"]["running"] = user_quota_data["used"]["running"] + 1
            self.check_quota(
                user_quota_data,
                "running",
                {
                    "error_description": user["name"]
                    + " quota exceeded for starting desktop",
                    "error_description_code": "desktop_start_user_quota_exceeded",
                },
            )

            # Add the desktop memory to check if starting it would exceed the quota
            user_quota_data["used"]["memory"] = (
                user_quota_data["used"]["memory"]
                + desktop["create_dict"]["hardware"]["memory"] / 1048576
            )

            self.check_quota(
                user_quota_data,
                "memory",
                {
                    "error_description": user["name"]
                    + " memory quota exceeded for starting desktop",
                    "error_description_code": "desktop_start_memory_quota_exceeded",
                },
            )

            # Add the desktop vcpus to check if starting it would exceed the quota
            user_quota_data["used"]["vcpus"] = (
                user_quota_data["used"]["vcpus"]
                + desktop["create_dict"]["hardware"]["vcpus"]
            )

            self.check_quota(
                user_quota_data,
                "vcpus",
                {
                    "error_description": user["name"]
                    + " vcpus quota exceeded for starting desktop",
                    "error_description_code": "desktop_start_vcpu_quota_exceeded",
                },
            )

            # Add 1GB to the desktop and parsing to GB to check if starting it would exceed the quota
            user_quota_data["used"]["total_size"] = (
                user_quota_data["used"]["total_size"] + 1
            )

            self.check_quota(
                user_quota_data,
                "total_size",
                {
                    "error_description": user["name"]
                    + " disk size quota exceeded for starting desktop",
                    "error_description_code": "total_size_quota_exceeded",
                },
            )

        # Group limits
        try:
            with app.app_context():
                group = (
                    r.table("groups")
                    .get(user["group"])
                    .pluck("name", "quota", "limits")
                    .run(db.conn)
                )
        except:
            raise Error("not_found", "Group not found")

        if group["limits"]:
            started_desktops = self.get_started_desktops(user["group"], "kind_group")
            desktops = {
                "running": started_desktops["count"] + 1,  # Add the current desktop
                "vcpus": started_desktops["vcpus"]
                + desktop["create_dict"]["hardware"]["vcpus"],
                "memory": started_desktops["memory"]
                + desktop["create_dict"]["hardware"]["memory"] / 1048576,
            }
            # Check running limits
            self.check_limits(
                item=group,
                quota_key="running",
                quantity=desktops["running"],
                limits_error={
                    "error_description": user["group_name"]
                    + " group limits exceeded for starting desktop",
                    "error_description_code": "desktop_start_group_limit_exceeded",
                },
            )
            # Check memory limits
            self.check_limits(
                item=group,
                quota_key="memory",
                quantity=desktops["memory"],
                limits_error={
                    "error_description": user["group_name"]
                    + " group memory limits exceeded for starting desktop",
                    "error_description_code": "desktop_start_group_memory_limit_exceeded",
                },
            )
            # Check vcpus limits
            self.check_limits(
                item=group,
                quota_key="vcpus",
                quantity=desktops["vcpus"],
                limits_error={
                    "error_description": user["group_name"]
                    + " group vcpu limits exceeded for starting desktop",
                    "error_description_code": "desktop_start_group_vcpu_limit_exceeded",
                },
            )

            # Get the group used disk size
            with app.app_context():
                total_size = (
                    r.table("users")
                    .get_all(user["group"], index="group")
                    .eq_join(
                        [r.row["id"], "ready"], r.table("storage"), index="user_status"
                    )
                    .sum(
                        lambda right: right["right"]["qemu-img-info"][
                            "actual-size"
                        ].default(0)
                    )
                    .run(db.conn)
                )
            with app.app_context():
                total_media_size = (
                    r.table("media")
                    .get_all(user["group"], index="group")
                    .sum(lambda size: size["progress"]["total_bytes"].default(0))
                    .run(db.conn)
                )
            # Add 1GB to the desktop and parsing to GB to check if starting it would exceed the group quota
            user_quota_data["used"]["total_size"] = (
                total_size + total_media_size
            ) / 1073741824 + 1

            self.check_limits(
                item=group,
                quota_key="total_size",
                quantity=user_quota_data["used"]["total_size"],
                limits_error={
                    "error_description": user["group_name"]
                    + " group disk size limits exceeded for starting desktop",
                    "error_description_code": "group_total_size_limit_exceeded",
                },
            )

        # Category limits
        try:
            with app.app_context():
                category = (
                    r.table("categories")
                    .get(user["category"])
                    .pluck("name", "quota", "limits")
                    .run(db.conn)
                )
        except:
            raise Error("not_found", "Category not found")

        # Category limit
        if not category["limits"]:
            return desktop

        started_desktops = self.get_started_desktops(user["category"], "kind_category")
        desktops = {
            "running": started_desktops["count"] + 1,  # Add the current desktop
            "vcpus": started_desktops["vcpus"]
            + desktop["create_dict"]["hardware"]["vcpus"],
            "memory": started_desktops["memory"]
            + desktop["create_dict"]["hardware"]["memory"] / 1048576,
        }
        # Check running limits
        self.check_limits(
            item=category,
            quota_key="running",
            quantity=desktops["running"],
            limits_error={
                "error_description": user["category_name"]
                + " category limits exceeded for starting desktop",
                "error_description_code": "desktop_start_category_limit_exceeded",
            },
        )
        # Check memory limits
        self.check_limits(
            item=category,
            quota_key="memory",
            quantity=desktops["memory"],
            limits_error={
                "error_description": user["category_name"]
                + " category memory limits exceeded for starting desktop",
                "error_description_code": "desktop_start_category_memory_limit_exceeded",
            },
        )
        # Check vcpus limits
        self.check_limits(
            item=category,
            quota_key="vcpus",
            quantity=desktops["vcpus"],
            limits_error={
                "error_description": user["category_name"]
                + " group vcpu limits exceeded for starting desktop",
                "error_description_code": "desktop_start_category_vcpu_limit_exceeded",
            },
        )

        # Get the category used disk size
        with app.app_context():
            total_size = (
                r.table("users")
                .get_all(user["category"], index="category")
                .eq_join(
                    [r.row["id"], "ready"], r.table("storage"), index="user_status"
                )
                .sum(
                    lambda right: right["right"]["qemu-img-info"][
                        "actual-size"
                    ].default(0)
                )
                .run(db.conn)
            )
        with app.app_context():
            total_media_size = (
                r.table("media")
                .get_all(user["category"], index="category")
                .sum(lambda size: size["progress"]["total_bytes"].default(0))
                .run(db.conn)
            )
        # Add 1GB to the desktop and parsing to GB to check if starting it would exceed the category quota
        user_quota_data["used"]["total_size"] = (
            total_size + total_media_size
        ) / 1073741824 + 1

        self.check_limits(
            item=category,
            quota_key="total_size",
            quantity=user_quota_data["used"]["total_size"],
            limits_error={
                "error_description": user["category_name"]
                + " category disk size limits exceeded for starting desktop",
                "error_description_code": "category_total_size_limit_exceeded",
            },
        )

        return desktop

    def deployment_desktop_start(self, user_id, desktop_id):
        with app.app_context():
            desktop = r.table("domains").get(desktop_id).run(db.conn)
        if not desktop:
            raise Error("not_found", "Desktop not found")
        elif not desktop["tag"]:
            raise Error("precondition_required", "Desktop is not part of a deployment")
        try:
            with app.app_context():
                user = (
                    r.table("users")
                    .get(user_id)
                    .merge(
                        lambda d: {
                            "category_name": r.table("categories").get(d["category"])[
                                "name"
                            ],
                            "group_name": r.table("groups").get(d["group"])["name"],
                            "role_name": r.table("roles").get(d["role"])["name"],
                        }
                    )
                    .pluck(
                        "id",
                        "name",
                        "category",
                        "group",
                        "role",
                        "quota",
                        "category_name",
                        "group_name",
                        "role_name",
                    )
                    .run(db.conn)
                )
            if user["role"] == "admin":
                return desktop
        except:
            raise Error("not_found", "User not found")

        self.check_field_quotas(
            user,
            "started_deployment_desktops",
            1,
            {
                "error_description": user["name"]
                + " quota exceeded for starting deployment desktops",
                "error_description_code": "deployment_start_user_quota_exceeded",
            },
        )

        ## Limits
        user_quota_data = self.Get(user_id=user["id"], started_info=True)

        # Group limits
        try:
            with app.app_context():
                group = (
                    r.table("groups")
                    .get(user["group"])
                    .pluck("name", "quota", "limits")
                    .run(db.conn)
                )
        except:
            raise Error("not_found", "Group not found")

        if group["limits"]:
            started_desktops = self.get_started_desktops(user["group"], "kind_group")
            desktops = {
                "running": started_desktops["count"] + 1,  # Add the current desktop
                "vcpus": started_desktops["vcpus"]
                + desktop["create_dict"]["hardware"]["vcpus"],
                "memory": started_desktops["memory"]
                + desktop["create_dict"]["hardware"]["memory"] / 1048576,
            }
            # Check running limits
            self.check_limits(
                item=group,
                quota_key="running",
                quantity=desktops["running"],
                limits_error={
                    "error_description": user["group_name"]
                    + " group limits exceeded for starting desktop",
                    "error_description_code": "desktop_start_group_limit_exceeded",
                },
            )
            # Check memory limits
            self.check_limits(
                item=group,
                quota_key="memory",
                quantity=desktops["memory"],
                limits_error={
                    "error_description": user["group_name"]
                    + " group memory limits exceeded for starting desktop",
                    "error_description_code": "desktop_start_group_memory_limit_exceeded",
                },
            )
            # Check vcpus limits
            self.check_limits(
                item=group,
                quota_key="vcpus",
                quantity=desktops["vcpus"],
                limits_error={
                    "error_description": user["group_name"]
                    + " group vcpu limits exceeded for starting desktop",
                    "error_description_code": "desktop_start_group_vcpu_limit_exceeded",
                },
            )

            # Get the group used disk size
            with app.app_context():
                total_size = (
                    r.table("users")
                    .get_all(user["group"], index="group")
                    .eq_join(
                        [r.row["id"], "ready"], r.table("storage"), index="user_status"
                    )
                    .sum(
                        lambda right: right["right"]["qemu-img-info"][
                            "actual-size"
                        ].default(0)
                    )
                    .run(db.conn)
                )
            with app.app_context():
                total_media_size = (
                    r.table("media")
                    .get_all(user["group"], index="group")
                    .sum(lambda size: size["progress"]["total_bytes"].default(0))
                    .run(db.conn)
                )
            # Add 1GB to the desktop and parsing to GB to check if starting it would exceed the group quota
            user_quota_data["used"]["total_size"] = (
                total_size + total_media_size
            ) / 1073741824 + 1

            self.check_limits(
                item=group,
                quota_key="total_size",
                quantity=user_quota_data["used"]["total_size"],
                limits_error={
                    "error_description": user["group_name"]
                    + " group disk size limits exceeded for starting desktop",
                    "error_description_code": "group_total_size_limit_exceeded",
                },
            )

        # Category limits
        try:
            with app.app_context():
                category = (
                    r.table("categories")
                    .get(user["category"])
                    .pluck("name", "quota", "limits")
                    .run(db.conn)
                )
        except:
            raise Error("not_found", "Category not found")

        # Category limit
        if not category["limits"]:
            return desktop

        started_desktops = self.get_started_desktops(user["category"], "kind_category")
        desktops = {
            "running": started_desktops["count"] + 1,  # Add the current desktop
            "vcpus": started_desktops["vcpus"]
            + desktop["create_dict"]["hardware"]["vcpus"],
            "memory": started_desktops["memory"]
            + desktop["create_dict"]["hardware"]["memory"] / 1048576,
        }
        # Check running limits
        self.check_limits(
            item=category,
            quota_key="running",
            quantity=desktops["running"],
            limits_error={
                "error_description": user["category_name"]
                + " category limits exceeded for starting desktop",
                "error_description_code": "desktop_start_category_limit_exceeded",
            },
        )
        # Check memory limits
        self.check_limits(
            item=category,
            quota_key="memory",
            quantity=desktops["memory"],
            limits_error={
                "error_description": user["category_name"]
                + " category memory limits exceeded for starting desktop",
                "error_description_code": "desktop_start_category_memory_limit_exceeded",
            },
        )
        # Check vcpus limits
        self.check_limits(
            item=category,
            quota_key="vcpus",
            quantity=desktops["vcpus"],
            limits_error={
                "error_description": user["category_name"]
                + " group vcpu limits exceeded for starting desktop",
                "error_description_code": "desktop_start_category_vcpu_limit_exceeded",
            },
        )

        # Get the category used disk size
        with app.app_context():
            total_size = (
                r.table("users")
                .get_all(user["category"], index="category")
                .eq_join(
                    [r.row["id"], "ready"], r.table("storage"), index="user_status"
                )
                .sum(
                    lambda right: right["right"]["qemu-img-info"][
                        "actual-size"
                    ].default(0)
                )
                .run(db.conn)
            )
        with app.app_context():
            total_media_size = (
                r.table("media")
                .get_all(user["category"], index="category")
                .sum(lambda size: size["progress"]["total_bytes"].default(0))
                .run(db.conn)
            )
        # Add 1GB to the desktop and parsing to GB to check if starting it would exceed the category quota
        user_quota_data["used"]["total_size"] = (
            total_size + total_media_size
        ) / 1073741824 + 1

        self.check_limits(
            item=category,
            quota_key="total_size",
            quantity=user_quota_data["used"]["total_size"],
            limits_error={
                "error_description": user["category_name"]
                + " category disk size limits exceeded for starting desktop",
                "error_description_code": "category_total_size_limit_exceeded",
            },
        )

        return desktop

    def deployment_create(self, users, owner_id, quantity=1):
        try:
            with app.app_context():
                user = (
                    r.table("users")
                    .get(owner_id)
                    .merge(
                        lambda d: {
                            "category_name": r.table("categories").get(d["category"])[
                                "name"
                            ],
                            "group_name": r.table("groups").get(d["group"])["name"],
                            "role_name": r.table("roles").get(d["role"])["name"],
                        }
                    )
                    .pluck(
                        "id",
                        "name",
                        "category",
                        "group",
                        "quota",
                        "category_name",
                        "group_name",
                        "role_name",
                    )
                    .run(db.conn)
                )
        except:
            raise Error("not_found", "User not found")

        with app.app_context():
            group_quantity = (
                r.table("deployments")
                .eq_join("user", r.table("users"))
                .filter({"right": {"group": user["group"]}})
                .count()
                .run(db.conn)
            )
        with app.app_context():
            category_quantity = (
                r.table("deployments")
                .eq_join("user", r.table("users"))
                .filter({"right": {"category": user["category"]}})
                .count()
                .run(db.conn)
            )
        quota_error = {
            "error_description": user["name"]
            + " quota exceeded for creating new deployments",
            "error_description_code": "deployment_new_user_quota_exceeded",
        }
        limits_error = {
            "group": {
                "error_description": user["group_name"]
                + " group limits exceeded for creating new deployments",
                "error_description_code": "deployments_new_group_limit_exceeded",
            },
            "category": {
                "error_description": user["name"]
                + " category limits exceeded for creating new deployments",
                "error_description_code": "deployments_new_category_limit_exceeded",
            },
        }
        self.check_field_quotas_and_limits(
            user,
            "deployments_total",
            quantity,
            quota_error,
            group_quantity,
            category_quantity,
            limits_error,
        )

        # Check the amount of desktops in the deployment
        quota_error = {
            "error_description": user["name"]
            + " quota exceeded for desktops in deployment",
            "error_description_code": "deployment_desktop_new_user_quota_exceeded",
        }
        self.check_field_quotas(
            user,
            "deployment_desktops",
            len(users),
            quota_error,
        )

        # Group the users considering its groups and categories
        groups_users = {}
        categories_users = {}
        for user in users:
            groups_users.setdefault(user["group"], []).append(user)
            categories_users.setdefault(user["category"], []).append(user)

        # Check the group limits aren't exceeded
        for group_id, users in groups_users.items():
            try:
                with app.app_context():
                    group = (
                        r.table("groups")
                        .get(group_id)
                        .pluck("name", "quota", "limits")
                        .run(db.conn)
                    )
            except:
                raise Error("not_found", "Group not found")

            if group["limits"]:
                with app.app_context():
                    group_domains = (
                        r.table("domains")
                        .get_all(["desktop", group_id], index="kind_group")
                        .count()
                        .run(db.conn)
                    )

                if group_domains + len(users) > group["limits"].get("desktops"):
                    raise Error(
                        "precondition_required",
                        "Group "
                        + group["name"]
                        + " limit exceeded for creating new desktop.",
                        traceback.format_exc(),
                        description_code="deployment_desktop_new_group_limit_exceeded",
                        params={"group": group["name"]},
                    )

        # Check the category limits aren't exceeded
        for category_id, users in categories_users.items():
            try:
                with app.app_context():
                    category = (
                        r.table("categories")
                        .get(user["category"])
                        .pluck("name", "quota", "limits")
                        .run(db.conn)
                    )
            except:
                raise Error("not_found", "Category not found")

            if category["limits"]:
                with app.app_context():
                    category_domains = (
                        r.table("domains")
                        .get_all(["desktop", category_id], index="kind_category")
                        .count()
                        .run(db.conn)
                    )

                if category_domains + len(users) > category["limits"].get("desktops"):
                    raise Error(
                        "precondition_required",
                        "Category "
                        + category_id
                        + " limit exceeded for creating new desktops",
                        traceback.format_exc(),
                        data=category_domains,
                        description_code="deployment_desktop_new_category_limit_exceeded",
                        params={"category": category["name"]},
                    )

    def deployment_update(self, users, owner_id):
        try:
            with app.app_context():
                user = (
                    r.table("users")
                    .get(owner_id)
                    .merge(
                        lambda d: {
                            "category_name": r.table("categories").get(d["category"])[
                                "name"
                            ],
                            "group_name": r.table("groups").get(d["group"])["name"],
                            "role_name": r.table("roles").get(d["role"])["name"],
                        }
                    )
                    .pluck(
                        "id",
                        "name",
                        "category",
                        "group",
                        "quota",
                        "category_name",
                        "group_name",
                        "role_name",
                    )
                    .run(db.conn)
                )
        except:
            raise Error("not_found", "User not found")

        # Check the amount of desktops in the deployment
        quota_error = {
            "error_description": user["name"]
            + " quota exceeded for desktops in deployment",
            "error_description_code": "deployment_desktop_new_user_quota_exceeded",
        }
        self.check_field_quotas(
            user,
            "deployment_desktops",
            len(users),
            quota_error,
        )

    def get_hardware_allowed(self, payload, domain_id=None):
        return self.user_hardware_allowed(payload, kind=None, domain_id=domain_id)

    def get_hardware_kind_allowed(self, payload, kind):
        return self.user_hardware_allowed(payload, kind, None)

    def limit_user_hardware_allowed(self, payload, create_dict):
        user_hardware = self.user_hardware_allowed(payload)
        limited = {}
        ## Limit the resources to the ones allowed to user
        if user_hardware["quota"] != False:
            if create_dict["hardware"]["vcpus"] > user_hardware["quota"]["vcpus"]:
                limited["vcpus"] = {
                    "old_value": create_dict["hardware"]["vcpus"],
                    "new_value": user_hardware["quota"]["vcpus"],
                }
                create_dict["hardware"]["vcpus"] = user_hardware["quota"]["vcpus"]
            if create_dict["hardware"]["memory"] > user_hardware["quota"]["memory"]:
                limited["memory"] = {
                    "old_value": create_dict["hardware"]["memory"],
                    "new_value": user_hardware["quota"]["memory"],
                }
                create_dict["hardware"]["memory"] = user_hardware["quota"]["memory"]

        if len(create_dict["hardware"].get("interfaces", [])):
            limited["interfaces"] = {"old_value": [], "new_value": []}
            interfaces_allowed = [uh["id"] for uh in user_hardware["interfaces"]]
            interfaces_requested = create_dict["hardware"]["interfaces"]
            for interface_requested in interfaces_requested:
                if interface_requested["id"] not in interfaces_allowed:
                    with app.app_context():
                        limited["interfaces"]["old_value"].append(
                            {
                                "id": interface_requested["id"],
                                "name": r.table("interfaces")
                                .get(interface_requested["id"])
                                .pluck("name")
                                .run(db.conn)["name"],
                            }
                        )

            create_dict["hardware"]["interfaces"] = [
                x
                for x in create_dict["hardware"]["interfaces"]
                if x["id"] not in [i["id"] for i in limited["interfaces"]["old_value"]]
            ]

            if not len(limited["interfaces"]["old_value"]):
                del limited["interfaces"]

            if not len(create_dict["hardware"]["interfaces"]):
                with app.app_context():
                    limited["interfaces"]["new_value"] = [
                        r.table("interfaces")
                        .get("default")
                        .pluck("id", "name")
                        .run(db.conn),
                    ]
                create_dict["hardware"]["interfaces"] = ["default"]

        if len(create_dict["hardware"].get("videos", [])):
            videos = [uh["id"] for uh in user_hardware["videos"]]
            for video in create_dict["hardware"]["videos"]:
                if video not in videos:
                    if "videos" not in limited:
                        with app.app_context():
                            limited["videos"] = {
                                "old_value": [
                                    {
                                        "id": video,
                                        "name": r.table("videos")
                                        .get(video)
                                        .pluck("name")
                                        .run(db.conn)["name"],
                                    }
                                ],
                                "new_value": [],
                            }
                    else:
                        limited["videos"]["old_value"].append(video)
                    create_dict["hardware"]["videos"].remove(video)
            if not len(create_dict["hardware"]["videos"]):
                with app.app_context():
                    limited["videos"]["new_value"] = [
                        r.table("videos")
                        .get("default")
                        .pluck("id", "name")
                        .run(db.conn),
                    ]
                create_dict["hardware"]["videos"] = ["default"]

        if len(create_dict["hardware"].get("graphics", [])):
            graphics = [uh["id"] for uh in user_hardware["graphics"]]
            for graphic in create_dict["hardware"]["graphics"]:
                if graphic not in graphics:
                    if "graphics" not in limited:
                        with app.app_context():
                            limited["graphics"] = {
                                "old_value": [
                                    {
                                        "id": graphic,
                                        "name": r.table("graphics")
                                        .get(graphic)
                                        .pluck("name")
                                        .run(db.conn)["name"],
                                    }
                                ],
                                "new_value": [],
                            }
                    else:
                        limited["graphics"]["old_value"].append(graphic)
                    create_dict["hardware"]["graphics"].remove(graphic)
            if not len(create_dict["hardware"]["graphics"]):
                with app.app_context():
                    limited["graphics"]["new_value"] = [
                        r.table("graphics")
                        .get("default")
                        .pluck("id", "name")
                        .run(db.conn),
                    ]
                create_dict["hardware"]["graphics"] = ["default"]

        if len(create_dict["hardware"].get("isos", [])):
            isos = allowed.get_items_allowed(
                payload,
                "media",
                query_pluck=["id", "name", "description"],
                query_filter={"status": "Downloaded"},
                index_key="kind",
                index_value="iso",
            )
            for iso in create_dict["hardware"]["isos"]:
                if iso["id"] not in [i["id"] for i in isos]:
                    if "isos" not in limited:
                        with app.app_context():
                            limited["isos"] = {
                                "old_value": [
                                    {
                                        "id": iso["id"],
                                        "name": r.table("media")
                                        .get(iso["id"])
                                        .pluck("name")
                                        .run(db.conn)["name"],
                                    }
                                ],
                                "new_value": [],
                            }
                    else:
                        limited["isos"]["old_value"].append(iso)
                    create_dict["hardware"]["isos"].remove(iso)

        if len(create_dict["hardware"].get("floppies", [])):
            floppies = allowed.get_items_allowed(
                payload,
                "media",
                query_pluck=["id", "name", "description"],
                query_filter={"status": "Downloaded"},
                index_key="kind",
                index_value="floppy",
            )
            for floppy in create_dict["hardware"]["floppies"]:
                if floppy["id"] not in [f["id"] for f in floppies]:
                    if "floppies" not in limited:
                        with app.app_context():
                            limited["floppies"] = {
                                "old_value": [
                                    {
                                        "id": floppy["id"],
                                        "name": r.table("media")
                                        .get(floppy["id"])
                                        .pluck("name")
                                        .run(db.conn)["name"],
                                    }
                                ],
                                "new_value": [],
                            }
                    else:
                        limited["floppies"]["old_value"].append(floppy)
                    create_dict["hardware"]["floppies"].remove(floppy)

        if len(create_dict["hardware"].get("boot_order", [])):
            boot_orders = [uh["id"] for uh in user_hardware["boot_order"]]
            for boot_order in create_dict["hardware"]["boot_order"]:
                if boot_order not in boot_orders:
                    if "boot_order" not in limited:
                        with app.app_context():
                            limited["boot_order"] = {
                                "old_value": [
                                    {
                                        "id": boot_order,
                                        "name": r.table("boots")
                                        .get(boot_order)
                                        .pluck("name")
                                        .run(db.conn)["name"],
                                    }
                                ],
                                "new_value": [],
                            }
                    else:
                        limited["boot_order"]["old_value"].append(boot_order)
                    create_dict["hardware"]["boot_order"].remove(boot_order)
            if not len(create_dict["hardware"]["boot_order"]):
                with app.app_context():
                    limited["boot_order"]["new_value"] = [
                        r.table("boots").get("disk").pluck("id", "name").run(db.conn),
                    ]
                create_dict["hardware"]["boot_order"] = ["disk"]

        # if create_dict["hardware"].get("qos_id"):
        #     if "qos_id" not in [uh["id"] for uh in user_hardware["qos_id"]]:
        #         limited["qos_id"] = {
        #             "old_value": create_dict["hardware"]["qos_id"],
        #             "new_value": "unlimited",
        #         }
        #         create_dict["hardware"]["qos_id"] = "unlimited"

        if create_dict.get("reservables", {}).get("vgpus") and len(
            create_dict.get("reservables", {}).get("vgpus", [])
        ):
            reservables_vgpus = [
                uh["id"] for uh in user_hardware["reservables"]["vgpus"]
            ]
            for reservables_vgpu in create_dict["reservables"]["vgpus"]:
                if reservables_vgpu not in reservables_vgpus:
                    if "vgpus" not in limited:
                        with app.app_context():
                            limited["vgpus"] = {
                                "old_value": [
                                    {
                                        "id": reservables_vgpu,
                                        "name": r.table("reservables_vgpus")
                                        .get(reservables_vgpu)
                                        .pluck("name")
                                        .run(db.conn)["name"],
                                    }
                                ],
                                "new_value": [],
                            }
                    else:
                        limited["vgpus"]["old_value"].append(reservables_vgpu)
                    create_dict["reservables"]["vgpus"].remove(reservables_vgpu)
            if not len(create_dict["reservables"]["vgpus"]):
                with app.app_context():
                    limited["vgpus"]["new_value"] = [
                        r.table("reservables_vgpus")
                        .get("None")
                        .pluck("id", "name")
                        .run(db.conn),
                    ]
                create_dict["reservables"]["vgpus"] = None

        if limited == {}:
            limited = None
        return {**create_dict, **{"limited_hardware": limited}}

    # Timeouts
    def get_shutdown_timeouts(self, payload, desktop_id=None):
        return qp.get_shutdown_timeouts(payload, desktop_id=None)

    def user_hardware_allowed(self, payload, kind=None, domain_id=None):
        if kind and kind not in [
            "interfaces",
            "graphics",
            "videos",
            "boot_order",
            "qos_id",
            "reservables",
            "forced_hyp",
            "favourite_hyp",
            "quota",
            "isos",
            "floppies",
            "disk_bus",
        ]:
            raise Error(
                "bad_request", "Hardware kind not found", traceback.format_exc()
            )
        if domain_id:
            with app.app_context():
                domain = r.table("domains").get(domain_id)["create_dict"].run(db.conn)
            if not domain:
                raise Error(
                    "not_found",
                    "Domain id not found",
                    traceback.format_exc(),
                    description_code="not_found",
                )
            domain["hardware"]["interfaces"] = [
                i["id"] for i in domain["hardware"]["interfaces"]
            ]
        else:
            domain = {}

        dict = {}
        if payload["role_id"] in ["admin", "manager"]:
            if domain.get("hardware"):
                dict["virtualization_nested"] = domain["hardware"].get(
                    "virtualization_nested", False
                )
            else:
                dict["virtualization_nested"] = False
        if not kind or kind == "interfaces":
            dict["interfaces"] = allowed.get_items_allowed(
                payload,
                "interfaces",
                query_pluck=["id", "name", "description"],
                order="name",
                query_merge=False,
                extra_ids_allowed=(
                    []
                    if "interfaces" not in domain.get("hardware", [])
                    else domain["hardware"]["interfaces"]
                ),
            )
        if not kind or kind == "graphics":
            dict["graphics"] = allowed.get_items_allowed(
                payload,
                "graphics",
                query_pluck=["id", "name", "description"],
                order="name",
                query_merge=False,
                extra_ids_allowed=(
                    []
                    if "graphics" not in domain.get("hardware", [])
                    else domain["hardware"]["graphics"]
                ),
            )
        if not kind or kind == "videos":
            dict["videos"] = allowed.get_items_allowed(
                payload,
                "videos",
                query_pluck=["id", "name", "description"],
                order="name",
                query_merge=False,
                extra_ids_allowed=(
                    []
                    if "videos" not in domain.get("hardware", [])
                    else domain["hardware"]["videos"]
                ),
            )
        if not kind or kind == "boot_order":
            dict["boot_order"] = allowed.get_items_allowed(
                payload,
                "boots",
                query_pluck=["id", "name", "description"],
                order="name",
                query_merge=False,
                extra_ids_allowed=(
                    []
                    if "boot_order" not in domain.get("hardware", [])
                    else domain["hardware"]["boot_order"]
                ),
            )
        if not kind or kind == "qos_id":
            dict["qos_id"] = allowed.get_items_allowed(
                payload,
                "qos_disk",
                query_pluck=["id", "name", "description"],
                order="name",
                query_merge=False,
                extra_ids_allowed=(
                    []
                    if "qos_disk" not in domain.get("hardware", [])
                    else domain["hardware"]["qos_disk"]
                ),
            )
        if not kind or kind == "reservables":
            dict["reservables"] = {
                "vgpus": allowed.get_items_allowed(
                    payload,
                    "reservables_vgpus",
                    query_pluck=["id", "name", "description"],
                    order="name",
                    query_merge=False,
                    extra_ids_allowed=(
                        []
                        if not domain.get("reservables", {}).get("vgpus")
                        else domain["reservables"]["vgpus"]
                    ),
                )
            }
        if not kind or kind == "disk_bus":
            dict["disk_bus"] = allowed.get_items_allowed(
                payload,
                "disk_bus",
                query_pluck=["id", "name", "description"],
                order="name",
                query_merge=False,
                extra_ids_allowed=(
                    []
                    if "disk_bus" not in domain.get("hardware", [])
                    else domain["hardware"]["disk_bus"]
                ),
            )
        if not kind or kind == "forced_hyp":
            dict["forced_hyp"] = []

        if not kind or kind == "favourite_hyp":
            dict["favourite_hyp"] = []

        if not kind or kind == "quota":
            quota = self.get_applied_quota(payload["user_id"])
        else:
            quota = {}

        dict = {**dict, **quota}
        return dict

    def get_user_migration_check_quota_config(self):
        with app.app_context():
            migration_quota_check = (
                r.table("config")
                .get(1)
                .pluck("user_migration")["user_migration"]["check_quotas"]
                .run(db.conn)
            )
        return migration_quota_check
