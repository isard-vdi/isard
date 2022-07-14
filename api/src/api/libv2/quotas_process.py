#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import traceback

from rethinkdb import RethinkDB

from api import app

from .api_allowed import ApiAllowed
from .api_exceptions import Error

allowed = ApiAllowed()
r = RethinkDB()
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)


class QuotasProcess:
    def __init__(self):
        None

    def get(self, user_id, category_id=False, admin=False):
        """Used by socketio to inform of user quotas"""
        userquotas = {}
        if user_id != False:
            with app.app_context():
                user = r.table("users").get(user_id).run(db.conn)
            if user == None:
                return userquotas
            userquotas = self.process_user_quota(user_id)
            if user["role"] == "manager":
                userquotas["limits"] = self.process_category_limits(
                    user_id, from_user_id=True
                )
            if user["role"] == "admin":
                userquotas["global"] = self.get_admin_usage()
        else:
            if category_id != False:
                userquotas["limits"] = self.process_category_limits(category_id)
            if admin == True:
                userquotas["global"] = self.get_admin_usage()
        return userquotas

    def process_user_quota(self, user_id):
        with app.app_context():
            user = r.table("users").get(user_id).without("password", "vpn").run(db.conn)

        with app.app_context():
            desktops = (
                r.table("domains")
                .get_all(user_id, index="user")
                .filter({"kind": "desktop"})
                .count()
                .run(db.conn)
            )
            desktopsup = (
                r.table("domains")
                .get_all(user_id, index="user")
                .filter({"kind": "desktop", "status": "Started"})
                .count()
                .run(db.conn)
            )
            templates = (
                r.table("domains")
                .get_all(user_id, index="user")
                .filter({"kind": "template"})
                .count()
                .run(db.conn)
            )
            isos = r.table("media").get_all(user_id, index="user").count().run(db.conn)

            starteds = (
                r.table("domains")
                .get_all(user_id, index="user")
                .filter({"status": "Started"})
                .pluck("hardware")
                .run(db.conn)
            )

        vcpus = 0
        memory = 0
        for s in starteds:
            vcpus = vcpus + s["hardware"]["vcpus"]
            memory = memory + s["hardware"]["memory"]
        memory = memory / 1000000

        if user["quota"] == False:
            qpdesktops = qpup = qptemplates = qpisos = qpvcpus = qpmemory = 0
            dq = rq = tq = iq = vq = mq = 9999
        else:
            qpdesktops = (
                desktops * 100 / user["quota"]["desktops"]
                if user["quota"]["desktops"]
                else 100
            )
            dq = user["quota"]["desktops"]

            qpup = (
                desktopsup * 100 / user["quota"]["running"]
                if user["quota"]["running"]
                else 100
            )
            rq = user["quota"]["running"]

            qptemplates = (
                templates * 100 / user["quota"]["templates"]
                if user["quota"]["templates"]
                else 100
            )
            tq = user["quota"]["templates"]

            qpisos = (
                isos * 100 / user["quota"]["isos"] if user["quota"]["isos"] else 100
            )
            iq = user["quota"]["isos"]

            qpvcpus = (
                vcpus * 100 / user["quota"]["vcpus"] if user["quota"]["vcpus"] else 100
            )
            vq = user["quota"]["vcpus"]

            qpmemory = (
                memory * 100 / user["quota"]["memory"]
                if user["quota"]["memory"]
                else 100
            )  # convert GB to KB (domains are in KB by default)
            mq = user["quota"]["memory"]

        return {
            "user": user,
            "d": desktops,
            "dq": dq,
            "dqp": int(round(qpdesktops, 0)),
            "r": desktopsup,
            "rq": rq,
            "rqp": int(round(qpup, 0)),
            "t": templates,
            "tq": tq,
            "tqp": int(round(qptemplates, 0)),
            "i": isos,
            "iq": iq,
            "iqp": int(round(qpisos, 0)),
            "v": vcpus,
            "vq": vq,
            "vqp": int(round(qpvcpus, 0)),
            "m": int(round(memory)),
            "mq": mq,
            "mqp": int(round(qpmemory, 0)),
        }

    def process_category_limits(self, id, from_user_id=None, from_group_id=None):
        if from_user_id:
            with app.app_context():
                user = r.table("users").get(id).pluck("category", "role").run(db.conn)
            id = user["category"]
        if from_group_id:
            with app.app_context():
                id = (
                    r.table("groups")
                    .get(id)
                    .pluck("parent_category")
                    .run(db.conn)["parent_category"]
                )

        with app.app_context():
            category = r.table("categories").get(id).run(db.conn)
        if (
            category == None
            or "limits" not in category.keys()
            or category["limits"] == False
        ):
            return False

        with app.app_context():
            desktops = (
                r.table("domains")
                .get_all(category["id"], index="category")
                .filter({"kind": "desktop"})
                .count()
                .run(db.conn)
            )
            desktopsup = (
                r.table("domains")
                .get_all(category["id"], index="category")
                .filter({"kind": "desktop", "status": "Started"})
                .count()
                .run(db.conn)
            )
            templates = (
                r.table("domains")
                .get_all(category["id"], index="category")
                .filter({"kind": "template"})
                .count()
                .run(db.conn)
            )
            isos = (
                r.table("media")
                .get_all(category["id"], index="category")
                .count()
                .run(db.conn)
            )

            starteds = (
                r.table("domains")
                .get_all(category["id"], index="category")
                .filter({"status": "Started"})
                .pluck("hardware")
                .run(db.conn)
            )

            users = (
                r.table("users")
                .get_all(category["id"], index="category")
                .count()
                .run(db.conn)
            )

        vcpus = 0
        memory = 0
        for s in starteds:
            vcpus = vcpus + s["hardware"]["vcpus"]
            memory = memory + s["hardware"]["memory"]
        memory = memory / 1000000

        if category["limits"] == False:
            qpdesktops = qpup = qptemplates = qpisos = qpvcpus = qpmemory = qpusers = 0
            dq = rq = tq = iq = vq = mq = uq = 9999
        else:
            qpdesktops = (
                desktops * 100 / category["limits"]["desktops"]
                if category["limits"]["desktops"]
                else 100
            )
            dq = category["limits"]["desktops"]

            qpup = (
                desktopsup * 100 / category["limits"]["running"]
                if category["limits"]["running"]
                else 100
            )
            rq = category["limits"]["running"]

            qptemplates = (
                templates * 100 / category["limits"]["templates"]
                if category["limits"]["templates"]
                else 100
            )
            tq = category["limits"]["templates"]

            qpisos = (
                isos * 100 / category["limits"]["isos"]
                if category["limits"]["isos"]
                else 100
            )
            iq = category["limits"]["isos"]

            qpvcpus = (
                vcpus * 100 / category["limits"]["vcpus"]
                if category["limits"]["vcpus"]
                else 100
            )
            vq = category["limits"]["vcpus"]

            qpmemory = (
                memory / category["limits"]["memory"]
                if category["limits"]["memory"]
                else 100
            )  # convert GB to KB (domains are in KB by default)
            mq = category["limits"]["memory"]

            qpusers = (
                users * 100 / category["limits"]["users"]
                if category["limits"]["users"]
                else 100
            )
            uq = category["limits"]["users"]

        return {
            "category": category,
            "d": desktops,
            "dq": dq,
            "dqp": int(round(qpdesktops, 0)),
            "r": desktopsup,
            "rq": rq,
            "rqp": int(round(qpup, 0)),
            "t": templates,
            "tq": tq,
            "tqp": int(round(qptemplates, 0)),
            "i": isos,
            "iq": iq,
            "iqp": int(round(qpisos, 0)),
            "v": vcpus,
            "vq": vq,
            "vqp": int(round(qpvcpus, 0)),
            "m": int(round(memory)),
            "mq": mq,
            "mqp": int(round(qpmemory, 0)),
            "u": users,
            "uq": uq,
            "uqp": int(round(qpusers, 0)),
        }

    def process_group_limits(self, id, from_user_id=None):
        if from_user_id:
            with app.app_context():
                user = r.table("users").get(id).pluck("group", "role").run(db.conn)
                group_id = user["group"]
        else:
            group_id = id

        with app.app_context():
            group = r.table("groups").get(group_id).run(db.conn)
        if group == None or "limits" not in group.keys() or group["limits"] == False:
            return False

        with app.app_context():
            desktops = (
                r.table("domains")
                .get_all(group["id"], index="group")
                .filter({"kind": "desktop"})
                .count()
                .run(db.conn)
            )
            desktopsup = (
                r.table("domains")
                .get_all(group["id"], index="group")
                .filter({"kind": "desktop", "status": "Started"})
                .count()
                .run(db.conn)
            )
            templates = (
                r.table("domains")
                .get_all(group["id"], index="group")
                .filter({"kind": "template"})
                .count()
                .run(db.conn)
            )
            isos = (
                r.table("media")
                .get_all(group["id"], index="group")
                .count()
                .run(db.conn)
            )

            starteds = (
                r.table("domains")
                .get_all(group["id"], index="group")
                .filter({"status": "Started"})
                .pluck("hardware")
                .run(db.conn)
            )

            users = (
                r.table("users")
                .get_all(group["id"], index="group")
                .count()
                .run(db.conn)
            )

        vcpus = 0
        memory = 0
        for s in starteds:
            vcpus = vcpus + s["hardware"]["vcpus"]
            memory = memory + s["hardware"]["memory"]
        memory = memory / 1000000

        if group["limits"] == False:
            qpdesktops = qpup = qptemplates = qpisos = qpvcpus = qpmemory = qpusers = 0
            dq = rq = tq = iq = vq = mq = uq = 9999
        else:
            qpdesktops = (
                desktops * 100 / group["limits"]["desktops"]
                if group["limits"]["desktops"]
                else 100
            )
            dq = group["limits"]["desktops"]

            qpup = (
                desktopsup * 100 / group["limits"]["running"]
                if group["limits"]["running"]
                else 100
            )
            rq = group["limits"]["running"]

            qptemplates = (
                templates * 100 / group["limits"]["templates"]
                if group["limits"]["templates"]
                else 100
            )
            tq = group["limits"]["templates"]

            qpisos = (
                isos * 100 / group["limits"]["isos"] if group["limits"]["isos"] else 100
            )
            iq = group["limits"]["isos"]

            qpvcpus = (
                vcpus * 100 / group["limits"]["vcpus"]
                if group["limits"]["vcpus"]
                else 100
            )
            vq = group["limits"]["vcpus"]

            qpmemory = (
                memory / group["limits"]["memory"] if group["limits"]["memory"] else 100
            )  # convert GB to KB (domains are in KB by default)
            mq = group["limits"]["memory"]

            qpusers = (
                users * 100 / group["limits"]["users"]
                if group["limits"]["users"]
                else 100
            )
            uq = group["limits"]["users"]

        return {
            "group": group,
            "d": desktops,
            "dq": dq,
            "dqp": int(round(qpdesktops, 0)),
            "r": desktopsup,
            "rq": rq,
            "rqp": int(round(qpup, 0)),
            "t": templates,
            "tq": tq,
            "tqp": int(round(qptemplates, 0)),
            "i": isos,
            "iq": iq,
            "iqp": int(round(qpisos, 0)),
            "v": vcpus,
            "vq": vq,
            "vqp": int(round(qpvcpus, 0)),
            "m": int(round(memory)),
            "mq": mq,
            "mqp": int(round(qpmemory, 0)),
            "u": users,
            "uq": uq,
            "uqp": int(round(qpusers, 0)),
        }

    def get_admin_usage(self):
        with app.app_context():
            desktops = (
                r.table("domains").get_all("desktop", index="kind").count().run(db.conn)
            )
            desktopsup = (
                r.table("domains")
                .get_all("Started", index="status")
                .count()
                .run(db.conn)
            )
            templates = (
                r.table("domains").filter({"kind": "template"}).count().run(db.conn)
            )
            isos = r.table("media").count().run(db.conn)
            starteds = (
                r.table("domains")
                .get_all("Started", index="status")
                .pluck("hardware")
                .run(db.conn)
            )
        vcpus = 0
        memory = 0
        for s in starteds:
            vcpus = vcpus + s["hardware"]["vcpus"]
            memory = memory + s["hardware"]["memory"]
        memory = memory / 1000000
        with app.app_context():
            users = r.table("users").count().run(db.conn)

        return {
            "d": desktops,
            "r": desktopsup,
            "t": templates,
            "i": isos,
            "v": vcpus,
            "m": int(round(memory)),
            "u": users,
        }

    def check(self, item, user_id, amount=1):
        """All common events should call here and check if quota/limits have exceeded already."""
        user = self.process_user_quota(user_id)
        group = self.process_group_limits(user_id, from_user_id=True)
        category = self.process_category_limits(user_id, from_user_id=True)
        if item == "NewDesktop":
            if user != False and float(user["dqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "User "
                    + user["user"]["name"]
                    + " quota exceeded for creating new desktop.",
                    traceback.format_exc(),
                    user,
                )
            if group != False and float(group["dqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "Group "
                    + group["group"]["name"]
                    + " quota exceeded for creating new desktop.",
                    traceback.format_exc(),
                    group,
                )
            if category != False and float(category["dqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "Category "
                    + category["category"]["name"]
                    + " quota exceeded for creating new desktop.",
                    traceback.format_exc(),
                    category,
                )

        if item == "NewConcurrent":
            if user != False:
                if float(user["rqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "User "
                        + user["user"]["name"]
                        + " quota exceeded for starting new desktop.",
                        traceback.format_exc(),
                        user,
                    )
                if float(user["vqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "User "
                        + user["user"]["name"]
                        + " quota exceeded for vCPU at starting a new desktop.",
                        traceback.format_exc(),
                        user,
                    )
                if float(user["mqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "User "
                        + user["user"]["name"]
                        + " quota exceeded for RAM at starting a new desktop.",
                        traceback.format_exc(),
                        user,
                    )
            if group != False:
                if float(group["rqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "Group "
                        + group["group"]["name"]
                        + " quota exceeded for starting new desktop.",
                        traceback.format_exc(),
                        group,
                    )
                if float(group["vqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "Group "
                        + group["group"]["name"]
                        + " quota exceeded for vCPU at starting new desktop.",
                        traceback.format_exc(),
                        group,
                    )
                if float(group["mqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "Group "
                        + group["group"]["name"]
                        + " quota exceeded for RAM at starting new desktop.",
                        traceback.format_exc(),
                        group,
                    )
            if category != False:
                if float(category["rqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "Category"
                        + category["category"]["name"]
                        + " quota exceeded for starting new desktop.",
                        traceback.format_exc(),
                        category,
                    )
                if float(category["vqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "Category"
                        + category["category"]["name"]
                        + " quota exceeded for vCPU at starting new desktop.",
                        traceback.format_exc(),
                        category,
                    )
                if float(category["mqp"]) >= 100:
                    raise Error(
                        "precondition_required",
                        "Category"
                        + category["category"]["name"]
                        + " quota exceeded for RAM at starting new desktop.",
                        traceback.format_exc(),
                        category,
                    )

        if item == "NewTemplate":
            if user != False and float(user["tqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "User "
                    + user["user"]["name"]
                    + " quota exceeded for creating new template.",
                    traceback.format_exc(),
                    user,
                )
            if group != False and float(group["tqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "Group "
                    + group["group"]["name"]
                    + " quota exceeded for creating new template.",
                    traceback.format_exc(),
                    group,
                )
            if category != False and float(category["tqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "Category "
                    + category["category"]["name"]
                    + " quota exceeded for creating new desktop.",
                    traceback.format_exc(),
                    category,
                )

        if item == "NewIso":
            if user != False and float(user["iqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "User "
                    + user["user"]["name"]
                    + " quota exceeded for uploading new iso",
                    traceback.format_exc(),
                    user,
                )
            if group != False and float(group["iqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "Group "
                    + group["group"]["name"]
                    + " quota exceeded for uploading new iso",
                    traceback.format_exc(),
                    group,
                )
            if category != False and float(category["iqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "Category "
                    + category["category"]["name"]
                    + " quota exceeded for uploading new iso",
                    traceback.format_exc(),
                    category,
                )

        if item == "NewUser":
            if group != False and float(group["uqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "Group "
                    + group["group"]["name"]
                    + " quota exceeded for creating user",
                    traceback.format_exc(),
                    group,
                )
            if category != False and float(category["uqp"]) >= 100:
                raise Error(
                    "precondition_required",
                    "Category "
                    + category["category"]["name"]
                    + " quota exceeded for creating user",
                    traceback.format_exc(),
                    category,
                )

        if item == "NewUsers":
            if group != False and group["u"] + amount > group["uq"]:
                raise Error(
                    "precondition_required",
                    "Group "
                    + group["group"]["name"]
                    + " quota exceeded for creating "
                    + str(amount)
                    + " users",
                    traceback.format_exc(),
                    group,
                )
            if category != False and category["u"] + amount > category["uq"]:
                raise Error(
                    "precondition_required",
                    "Category "
                    + category["category"]["name"]
                    + " quota exceeded for creating "
                    + str(amount)
                    + " users",
                    traceback.format_exc(),
                    category,
                )

        return False

    def check_new_autoregistered_user(self, category_id, group_id):
        """All common events should call here and check if quota/limits have exceeded already."""
        group = self.process_group_limits(group_id, from_user_id=False)
        category = self.process_category_limits(category_id, from_user_id=False)

        if group != False and float(group["uqp"]) >= 100:
            raise Error(
                "precondition_required",
                "Group " + group["group"]["name"] + " quota exceeded for creating user",
                traceback.format_exc(),
                group,
            )
        if category != False and float(category["uqp"]) >= 100:
            raise Error(
                "precondition_required",
                "Category "
                + category["category"]["name"]
                + " quota exceeded for creating user",
                traceback.format_exc(),
                category,
            )

        return False

    """ Used to edit category/group/user in admin """

    def get_category(self, category_id):
        with app.app_context():
            category = r.table("categories").get(category_id).run(db.conn)
        return {
            "quota": category["quota"],
            "limits": category["limits"] if "limits" in category else False,
        }

    def get_group(self, group_id):
        ### Limits for group will be at least limits for its category
        with app.app_context():
            group = r.table("groups").get(group_id).run(db.conn)
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

    def get_user(self, user_id):
        with app.app_context():
            user = r.table("users").get(user_id).run(db.conn)
            group = r.table("groups").get(user["group"]).run(db.conn)
        limits = group["limits"]
        if limits == False:
            with app.app_context():
                limits = (
                    r.table("categories")
                    .get(group["parent_category"])
                    .pluck("limits")
                    .run(db.conn)["limits"]
                )
        return {"quota": user["quota"], "limits": limits}

    def user_hardware_allowed(self, payload):
        dict = {}
        dict["nets"] = allowed.get_items_allowed(
            payload,
            "interfaces",
            query_pluck=["id", "name", "description"],
            order="name",
            query_merge=False,
        )
        dict["graphics"] = allowed.get_items_allowed(
            payload,
            "graphics",
            query_pluck=["id", "name", "description"],
            order="name",
            query_merge=False,
        )
        dict["videos"] = allowed.get_items_allowed(
            payload,
            "videos",
            query_pluck=["id", "name", "description"],
            order="name",
            query_merge=False,
        )
        dict["boots"] = allowed.get_items_allowed(
            payload,
            "boots",
            query_pluck=["id", "name", "description"],
            order="name",
            query_merge=False,
        )
        dict["qos_id"] = allowed.get_items_allowed(
            payload,
            "qos_disk",
            query_pluck=["id", "name", "description"],
            order="name",
            query_merge=False,
        )

        dict["hypervisors_pools"] = allowed.get_items_allowed(
            payload,
            "hypervisors_pools",
            query_pluck=["id", "name", "description"],
            order="name",
            query_merge=False,
        )
        dict["forced_hyp"] = []

        quota = self.get_user(payload["user_id"])
        dict = {**dict, **quota}
        return dict

    def limit_user_hardware_allowed(self, create_dict, user_id):
        user_hardware = self.user_hardware_allowed(user_id)
        ## Limit the resources to the ones allowed to user
        if user_hardware["quota"] != False:
            if create_dict["hardware"]["vcpus"] > user_hardware["quota"]["vcpus"]:
                create_dict["hardware"]["vcpus"] = user_hardware["quota"]["vcpus"]
            if (
                create_dict["hardware"]["memory"]
                > user_hardware["quota"]["memory"] * 1048576
            ):
                create_dict["hardware"]["memory"] = (
                    user_hardware["quota"]["memory"] * 1048576
                )

        if (
            create_dict["hardware"].get("videos")
            and len(create_dict["hardware"].get("videos", []))
            and create_dict["hardware"]["videos"][0]
            not in [uh["id"] for uh in user_hardware["videos"]]
        ):
            create_dict["hardware"]["videos"] = ["default"]

        if (
            create_dict["hardware"].get("interfaces")
            and len(create_dict["hardware"].get("interfaces", []))
            and create_dict["hardware"]["interfaces"][0]
            not in [uh["id"] for uh in user_hardware["nets"]]
        ):
            create_dict["hardware"]["interfaces"] = ["default"]

        if (
            create_dict["hardware"].get("graphics")
            and len(create_dict["hardware"].get("graphics", []))
            and create_dict["hardware"]["graphics"][0]
            not in [uh["id"] for uh in user_hardware["graphics"]]
        ):
            create_dict["hardware"]["graphics"] = ["default"]

        if (
            create_dict["hardware"].get("boot_order")
            and len(create_dict["hardware"].get("boot_order", []))
            and create_dict["hardware"]["boot_order"][0]
            not in [uh["id"] for uh in user_hardware["boots"]]
        ):
            create_dict["hardware"]["boot_order"] = ["hd"]

        if (
            create_dict["hardware"].get("qos_id")
            and len(create_dict["hardware"].get("qos_id", []))
            and create_dict["hardware"]["qos_id"]
            not in [uh["id"] for uh in user_hardware["qos_id"]]
        ):
            create_dict["hardware"]["qos_id"] = "unlimited"

        return create_dict
