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

from rethinkdb.errors import ReqlNonExistenceError

from .api_exceptions import Error
from .quotas_process import QuotasProcess

qp = QuotasProcess()


class Quotas:
    def __init__(self):
        None

    # Return the user applied quota or limit
    def Get(self, user_id):
        with app.app_context():
            user = (
                r.table("users")
                .get(user_id)
                .pluck("id", "name", "category", "group", "quota")
                .run(db.conn)
            )
            group = (
                r.table("groups").get(user["group"]).pluck("name", "quota").run(db.conn)
            )
            category = (
                r.table("categories")
                .get(user["category"])
                .pluck("name", "quota")
                .run(db.conn)
            )

            user_desktops = (
                r.table("domains")
                .get_all(["desktop", user_id, False], index="kind_user_tag")
                .count()
                .run(db.conn)
            )
            user_templates = (
                r.table("domains")
                .get_all(["template", user_id, False], index="kind_user_tag")
                .count()
                .run(db.conn)
            )
            user_media = (
                r.table("media").get_all(user_id, index="user").count().run(db.conn)
            )

        started_desktops = self.get_started_desktops(user_id, "kind_user")

        used = {
            "desktops": user_desktops,
            "templates": user_templates,
            "media": user_media,
            "running": started_desktops["count"],
            "memory": started_desktops["memory"],
            "vcpus": started_desktops["vcpus"],
        }

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

    def GetCategoryQuota(self, category_id):
        return qp.get_category(category_id)

    def GetGroupQuota(self, group_id):
        return qp.get_group(group_id)

    def UserCreate(self, category_id, group_id):
        qp.check_new_autoregistered_user(category_id, group_id)

    def TemplateCreate(self, user_id):
        self.DomainCreate(user_id, kind="template", quota_key="templates")

    def DesktopCreate(self, user_id):
        self.DomainCreate(user_id, kind="desktop", quota_key="desktops")

    def DomainCreate(self, user_id, kind="desktop", quota_key="desktops"):
        try:
            with app.app_context():
                user = (
                    r.table("users")
                    .get(user_id)
                    .pluck("id", "name", "category", "group", "quota")
                    .run(db.conn)
                )
        except:
            raise Error("not_found", "User not found")

        # User quota
        with app.app_context():
            user_domains = (
                r.table("domains")
                .get_all([kind, user["id"], False], index="kind_user_tag")
                .count()
                .run(db.conn)
            )
        if user["quota"]:
            if user_domains >= user["quota"].get(quota_key):
                raise Error(
                    "precondition_required",
                    "User " + user["name"] + " quota exceeded for creating new " + kind,
                    traceback.format_exc(),
                    data=user_domains,
                    description_code=kind + "_new_user_quota_exceeded",
                )

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

        with app.app_context():
            group_domains = (
                r.table("domains")
                .get_all([kind, user["group"]], index="kind_group")
                .count()
                .run(db.conn)
            )

        # Group quota
        if group["quota"] and user_domains >= group["quota"][quota_key]:
            raise Error(
                "precondition_required",
                "Group " + group["name"] + " quota exceeded for creating new " + kind,
                traceback.format_exc(),
                data=user_domains,
                description_code=kind + "_new_group_quota_exceeded",
            )

        # Group limit
        if group["limits"] and group_domains >= group["limits"][quota_key]:
            raise Error(
                "precondition_required",
                "Group " + user["group"] + " limit exceeded for creating new " + kind,
                traceback.format_exc(),
                data=group_domains,
                description_code=kind + "_new_group_limit_exceeded",
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

        with app.app_context():
            category_domains = (
                r.table("domains")
                .get_all([kind, user["category"]], index="kind_category")
                .count()
                .run(db.conn)
            )

        # Category quota
        if category["quota"] and user_domains >= category["quota"][quota_key]:
            raise Error(
                "precondition_required",
                "Category "
                + user["category"]
                + " quota exceeded for creating new "
                + kind,
                traceback.format_exc(),
                data=user_domains,
                description_code=kind + "_new_category_quota_exceeded",
            )

        # Category limit
        if not category["limits"]:
            return

        if category_domains >= category["limits"][quota_key]:
            raise Error(
                "precondition_required",
                "Category "
                + user["category"]
                + " limit exceeded for creating new "
                + kind,
                traceback.format_exc(),
                data=category_domains,
                description_code=kind + "_new_category_limit_exceeded",
            )

    def get_started_desktops(self, query_id, query_index):
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

    def DesktopStart(self, user_id, desktop_id):
        with app.app_context():
            desktop = r.table("domains").get(desktop_id).run(db.conn)
        if not desktop:
            raise Error("not_found", "Desktop not found")
        try:
            with app.app_context():
                user = (
                    r.table("users")
                    .get(user_id)
                    .pluck("id", "name", "category", "group", "quota")
                    .run(db.conn)
                )
        except:
            raise Error("not_found", "User not found")

        started_desktops = self.get_started_desktops(user_id, "kind_user")

        desktops = {
            "count": started_desktops["count"] + 1,  # Add the current desktop
            "vcpus": started_desktops["vcpus"]
            + desktop["create_dict"]["hardware"]["vcpus"],
            "memory": started_desktops["memory"]
            + desktop["create_dict"]["hardware"]["memory"] / 1048576,
        }

        # User quota
        if user["quota"]:
            if desktops["count"] > user["quota"].get("running"):
                raise Error(
                    "precondition_required",
                    "User "
                    + user["name"]
                    + " quota exceeded for starting new desktop.",
                    traceback.format_exc(),
                    data=desktops,
                    description_code="desktop_start_user_quota_exceeded",
                )
            if desktops["memory"] > user["quota"].get("memory"):
                raise Error(
                    "precondition_required",
                    "User "
                    + user["name"]
                    + " quota exceeded for memory at starting new desktop.",
                    traceback.format_exc(),
                    data=desktops,
                    description_code="desktop_start_memory_quota_exceeded",
                )
            if desktops["vcpus"] > user["quota"].get("vcpus"):
                raise Error(
                    "precondition_required",
                    "User "
                    + user["name"]
                    + " quota exceeded for vCPUs at starting new desktop.",
                    traceback.format_exc(),
                    data=desktops,
                    description_code="desktop_start_vcpu_quota_exceeded",
                )

        # Group quota
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

        if group["quota"]:
            if desktops["count"] > group["quota"].get("running"):
                raise Error(
                    "precondition_required",
                    "Group "
                    + group["name"]
                    + " quota exceeded for starting new desktop.",
                    traceback.format_exc(),
                    data=desktops,
                    description_code="desktop_start_group_quota_exceeded",
                )
            if desktops["memory"] > group["quota"].get("memory"):
                raise Error(
                    "precondition_required",
                    "Group "
                    + group["name"]
                    + " quota exceeded for memory at starting new desktop.",
                    traceback.format_exc(),
                    data=desktops,
                    description_code="desktop_start_group_memory_quota_exceeded",
                )
            if desktops["vcpus"] > group["quota"].get("vcpus"):
                raise Error(
                    "precondition_required",
                    "Group "
                    + group["name"]
                    + " quota exceeded for vCPUs at starting new desktop.",
                    traceback.format_exc(),
                    data=desktops,
                    description_code="desktop_start_group_vcpu_quota_exceeded",
                )

        # Group limit
        if group["limits"]:

            started_desktops = self.get_started_desktops(user["group"], "kind_group")

            desktops = {
                "count": started_desktops["count"] + 1,  # Add the current desktop
                "vcpus": started_desktops["vcpus"]
                + desktop["create_dict"]["hardware"]["vcpus"],
                "memory": started_desktops["memory"]
                + desktop["create_dict"]["hardware"]["memory"] / 1048576,
            }
            if desktops["count"] > group["limits"].get("running"):
                raise Error(
                    "precondition_required",
                    "Group "
                    + group["name"]
                    + " limit exceeded for starting new desktop.",
                    traceback.format_exc(),
                    data=desktops,
                    description_code="desktop_start_group_limit_exceeded",
                )
            if desktops["memory"] > group["limits"].get("memory"):
                raise Error(
                    "precondition_required",
                    "Group "
                    + group["name"]
                    + " limit exceeded for memory at starting new desktop.",
                    traceback.format_exc(),
                    data=desktops,
                    description_code="desktop_start_group_memory_limit_exceeded",
                )
            if desktops["vcpus"] > group["limits"].get("vcpus"):
                raise Error(
                    "precondition_required",
                    "Group "
                    + group["name"]
                    + " limit exceeded for vCPUs at starting new desktop.",
                    traceback.format_exc(),
                    data=desktops,
                    description_code="desktop_start_group_vcpu_limit_exceeded",
                )

        # Category quota
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

        if category["quota"]:
            if desktops["count"] > category["quota"].get("running"):
                raise Error(
                    "precondition_required",
                    "Category "
                    + category["name"]
                    + " quota exceeded for starting new desktop.",
                    traceback.format_exc(),
                    data=desktops,
                    description_code="desktop_start_category_quota_exceeded",
                )
            if desktops["memory"] > category["quota"].get("memory"):
                raise Error(
                    "precondition_required",
                    "Category "
                    + category["name"]
                    + " quota exceeded for memory at starting new desktop.",
                    traceback.format_exc(),
                    data=desktops,
                    description_code="desktop_start_category_memory_quota_exceeded",
                )
            if desktops["vcpus"] > category["quota"].get("vcpus"):
                raise Error(
                    "precondition_required",
                    "Category "
                    + category["name"]
                    + " quota exceeded for vCPUs at starting new desktop.",
                    traceback.format_exc(),
                    data=desktops,
                    description_code="desktop_start_category_vcpu_quota_exceeded",
                )

        # Category limit
        if not category["limits"]:
            return

        started_desktops = self.get_started_desktops(user["category"], "kind_category")

        desktops = {
            "count": started_desktops["count"] + 1,  # Add the current desktop
            "vcpus": started_desktops["vcpus"]
            + desktop["create_dict"]["hardware"]["vcpus"],
            "memory": started_desktops["memory"]
            + desktop["create_dict"]["hardware"]["memory"] / 1048576,
        }

        if desktops["count"] > category["limits"].get("running"):
            raise Error(
                "precondition_required",
                "Category "
                + category["name"]
                + " limit exceeded for starting new desktop.",
                traceback.format_exc(),
                data=desktops,
                description_code="desktop_start_category_limit_exceeded",
            )
        if desktops["memory"] > category["limits"].get("memory"):
            raise Error(
                "precondition_required",
                "Category "
                + category["name"]
                + " limit exceeded for memory at starting new desktop.",
                traceback.format_exc(),
                data=desktops,
                description_code="desktop_start_category_memory_limit_exceeded",
            )
        if desktops["vcpus"] > category["limits"].get("vcpus"):
            raise Error(
                "precondition_required",
                "Category "
                + category["name"]
                + " limit exceeded for vCPUs at starting new desktop.",
                traceback.format_exc(),
                data=desktops,
                description_code="desktop_start_category_vcpu_limit_exceeded",
            )

    def MediaCreate(self, user_id):
        try:
            with app.app_context():
                user = (
                    r.table("users")
                    .get(user_id)
                    .pluck("id", "name", "category", "group", "quota")
                    .run(db.conn)
                )
        except:
            raise Error("not_found", "User not found")

        # User quota
        with app.app_context():
            user_media = (
                r.table("media").get_all(user["id"], index="user").count().run(db.conn)
            )
        if user["quota"]:
            if user_media >= user["quota"].get("isos"):
                raise Error(
                    "precondition_required",
                    "User " + user["name"] + " quota exceeded for uploading new media.",
                    traceback.format_exc(),
                    data=user_media,
                    description_code="media_new_user_quota_exceeded",
                )

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

        with app.app_context():
            group_media = (
                r.table("media")
                .get_all(user["group"], index="group")
                .count()
                .run(db.conn)
            )

        # Group quota
        if group["quota"] and user_media >= group["quota"]["isos"]:
            raise Error(
                "precondition_required",
                "Group " + user["group"] + " quota exceeded for uploading new media.",
                traceback.format_exc(),
                data=user_media,
                description_code="media_new_group_quota_exceeded",
            )

        # Group limit
        if group["limits"] and group_media >= group["limits"]["isos"]:
            raise Error(
                "precondition_required",
                "Group " + user["group"] + " limit exceeded for uploading new media.",
                traceback.format_exc(),
                data=group_media,
                description_code="media_new_group_limit_exceeded",
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

        with app.app_context():
            category_media = (
                r.table("media")
                .get_all(user["category"], index="category")
                .count()
                .run(db.conn)
            )

        # Category quota
        if category["quota"] and user_media >= category["quota"]["isos"]:
            raise Error(
                "precondition_required",
                "Category "
                + user["category"]
                + " quota exceeded for uploading new media.",
                traceback.format_exc(),
                data=user_media,
                description_code="media_new_category_quota_exceeded",
            )

        # Category limit
        if not category["limits"]:
            return

        if category_media >= category["limits"]["isos"]:
            raise Error(
                "precondition_required",
                "Category "
                + user["category"]
                + " limit exceeded for creating new media.",
                traceback.format_exc(),
                data=category_media,
                description_code="media_new_category_limit_exceeded",
            )

    def deployment_create(self, users):
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

    def get_hardware_allowed(self, payload, domain_id=None):
        return qp.user_hardware_allowed(payload, kind=None, domain_id=domain_id)

    def get_hardware_kind_allowed(self, payload, kind):
        return qp.user_hardware_allowed(payload, kind, None)

    def limit_user_hardware_allowed(self, payload, create_dict):
        return qp.limit_user_hardware_allowed(payload, create_dict)

    # Timeouts
    def get_shutdown_timeouts(self, payload, desktop_id=None):
        return qp.get_shutdown_timeouts(payload, desktop_id=None)
