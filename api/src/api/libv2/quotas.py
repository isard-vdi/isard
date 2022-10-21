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

from .._common.api_exceptions import Error
from .api_allowed import ApiAllowed
from .quotas_process import QuotasProcess

allowed = ApiAllowed()

qp = QuotasProcess()


class Quotas:
    def __init__(self):
        None

    # Get in user["quota"] the applied quota, either user, group or category
    def Get(self, user_id, started_info=True):
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

            # Used
            user_desktops = (
                r.table("domains")
                .get_all(["desktop", user_id, False], index="kind_user_tag")
                .count()
                .run(db.conn)
            )
            user_templates = (
                r.table("domains")
                .get_all(["template", user_id, False], index="kind_user_tag")
                .filter({"enabled": True})
                .count()
                .run(db.conn)
            )
            user_media = (
                r.table("media").get_all(user_id, index="user").count().run(db.conn)
            )

        used = {
            "desktops": user_desktops,
            "templates": user_templates,
            "isos": user_media,
        }

        if started_info:
            started_desktops = self.get_started_desktops(user_id, "kind_user")
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

    def GetCategoryQuota(self, category_id):
        return qp.get_category(category_id)

    def GetGroupQuota(self, group_id):
        return qp.get_group(group_id)

    def UserCreate(self, category_id, group_id):
        qp.check_new_autoregistered_user(category_id, group_id)

    def desktop_create(self, user_id):
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
                .count()
                .run(db.conn)
            )
        with app.app_context():
            category_quantity = (
                r.table("domains")
                .get_all(["desktop", user["category"]], index="kind_category")
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
        self.create(
            user,
            "desktops",
            quota_error,
            group_quantity,
            category_quantity,
            limits_error,
        )

    def template_create(self, user_id):
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
            + " quota exceeded for creating new desktop",
            "error_description_code": "template_new_user_quota_exceeded",
        }
        limits_error = {
            "group": {
                "error_description": user["group_name"]
                + " group limits exceeded for creating new desktop",
                "error_description_code": "template_new_group_limit_exceeded",
            },
            "category": {
                "error_description": user["name"]
                + " category limits exceeded for creating new desktop",
                "error_description_code": "template_new_category_limit_exceeded",
            },
        }
        self.create(
            user,
            "templates",
            quota_error,
            group_quantity,
            category_quantity,
            limits_error,
        )

    def media_create(self, user_id):
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
            + " quota exceeded for creating new desktop",
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
        self.create(
            user,
            "isos",
            quota_error,
            group_quantity,
            category_quantity,
            limits_error,
        )

    def create(
        self,
        user,
        quota_key,
        quota_error,
        group_quantity,
        category_quantity,
        limits_error,
    ):

        # We get the user applied quota and currently used info to check the quota
        user_quota_data = self.Get(user_id=user["id"], started_info=False)
        if user_quota_data["quota"]:
            user_quota_data["used"][quota_key] = user_quota_data["used"][quota_key] + 1
            self.check_quota(user_quota_data, quota_key, quota_error)

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
                quantity=group_quantity + 1,
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
                quantity=category_quantity + 1,
                limits_error=limits_error["category"],
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
                        "quota",
                        "category_name",
                        "group_name",
                        "role_name",
                    )
                    .run(db.conn)
                )
        except:
            raise Error("not_found", "User not found")

        # We get the user applied quota and currently used info to check the quota
        user_quota_data = self.Get(user_id=user["id"], started_info=True)
        if user_quota_data["quota"]:
            user_quota_data["used"]["running"] = user_quota_data["used"]["running"] + 1
            user_quota_data["used"]["vcpus"] = (
                user_quota_data["used"]["vcpus"]
                + desktop["create_dict"]["hardware"]["vcpus"]
            )
            user_quota_data["used"]["memory"] = (
                user_quota_data["used"]["memory"]
                + desktop["create_dict"]["hardware"]["memory"] / 1048576
            )

            # Check running
            self.check_quota(
                user_quota_data,
                "running",
                {
                    "error_description": user["name"]
                    + " quota exceeded for starting desktop",
                    "error_description_code": "desktop_start_user_quota_exceeded",
                },
            )
            # Check memory
            self.check_quota(
                user_quota_data,
                "memory",
                {
                    "error_description": user["name"]
                    + " memory quota exceeded for starting desktop",
                    "error_description_code": "desktop_start_memory_quota_exceeded",
                },
            )
            # Check vcpus
            self.check_quota(
                user_quota_data,
                "vcpus",
                {
                    "error_description": user["name"]
                    + " vcpus quota exceeded for starting desktop",
                    "error_description_code": "desktop_start_vcpu_quota_exceeded",
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
            return

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
            interfaces = [uh["id"] for uh in user_hardware["interfaces"]]
            for interface in create_dict["hardware"]["interfaces"]:
                if interface not in interfaces:
                    if "interfaces" not in limited:
                        limited["interfaces"] = {
                            "old_value": [
                                {
                                    "id": interface,
                                    "name": r.table("interfaces")
                                    .get(interface)
                                    .pluck("name")
                                    .run(db.conn)["name"],
                                }
                            ],
                            "new_value": [],
                        }
                    else:
                        limited["interfaces"]["old_value"].append(interface)
                    create_dict["hardware"]["interfaces"].remove(interface)
            if not len(create_dict["hardware"]["interfaces"]):
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
                limited["videos"]["new_value"] = [
                    r.table("videos").get("default").pluck("id", "name").run(db.conn),
                ]
                create_dict["hardware"]["videos"] = ["default"]

        if len(create_dict["hardware"].get("graphics", [])):
            graphics = [uh["id"] for uh in user_hardware["graphics"]]
            for graphic in create_dict["hardware"]["graphics"]:
                if graphic not in graphics:
                    if "graphics" not in limited:
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
                limited["graphics"]["new_value"] = [
                    r.table("graphics").get("default").pluck("id", "name").run(db.conn),
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
                extra_ids_allowed=[]
                if "interfaces" not in domain.get("hardware", [])
                else domain["hardware"]["interfaces"],
            )
        if not kind or kind == "graphics":
            dict["graphics"] = allowed.get_items_allowed(
                payload,
                "graphics",
                query_pluck=["id", "name", "description"],
                order="name",
                query_merge=False,
                extra_ids_allowed=[]
                if "graphics" not in domain.get("hardware", [])
                else domain["hardware"]["graphics"],
            )
        if not kind or kind == "videos":
            dict["videos"] = allowed.get_items_allowed(
                payload,
                "videos",
                query_pluck=["id", "name", "description"],
                order="name",
                query_merge=False,
                extra_ids_allowed=[]
                if "videos" not in domain.get("hardware", [])
                else domain["hardware"]["videos"],
            )
        if not kind or kind == "boot_order":
            dict["boot_order"] = allowed.get_items_allowed(
                payload,
                "boots",
                query_pluck=["id", "name", "description"],
                order="name",
                query_merge=False,
                extra_ids_allowed=[]
                if "boot_order" not in domain.get("hardware", [])
                else domain["hardware"]["boot_order"],
            )
        if not kind or kind == "qos_id":
            dict["qos_id"] = allowed.get_items_allowed(
                payload,
                "qos_disk",
                query_pluck=["id", "name", "description"],
                order="name",
                query_merge=False,
                extra_ids_allowed=[]
                if "qos_disk" not in domain.get("hardware", [])
                else domain["hardware"]["qos_disk"],
            )
        if not kind or kind == "reservables":
            dict["reservables"] = {
                "vgpus": allowed.get_items_allowed(
                    payload,
                    "reservables_vgpus",
                    query_pluck=["id", "name", "description"],
                    order="name",
                    query_merge=False,
                    extra_ids_allowed=[]
                    if not domain.get("reservables", {}).get("vgpus")
                    else domain["reservables"]["vgpus"],
                )
            }
        if not kind or kind == "disk_bus":
            dict["disk_bus"] = allowed.get_items_allowed(
                payload,
                "disk_bus",
                query_pluck=["id", "name", "description"],
                order="name",
                query_merge=False,
                extra_ids_allowed=[]
                if "disk_bus" not in domain.get("hardware", [])
                else domain["hardware"]["disk_bus"],
            )
        if not kind or kind == "forced_hyp":
            dict["forced_hyp"] = []

        if not kind or kind == "quota":
            quota = self.Get(payload["user_id"])
        else:
            quota = {}

        dict = {**dict, **quota}
        return dict
