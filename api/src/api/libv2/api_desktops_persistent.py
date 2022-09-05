#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import secrets
import time
import traceback

from ..libv2.quotas import Quotas

quotas = Quotas()

from rethinkdb import RethinkDB

from api import app

from ..libv2.validators import _validate_item, check_user_duplicated_domain_name
from .api_exceptions import Error

r = RethinkDB()

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..libv2.isardViewer import isardViewer

isardviewer = isardViewer()

from ..libv2.api_cards import ApiCards, get_domain_stock_card

api_cards = ApiCards()

from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.quotas_process import QuotasProcess

qp = QuotasProcess()

from .ds import DS

ds = DS()

from .helpers import (
    _check,
    _parse_media_info,
    _parse_string,
    default_guest_properties,
    gen_payload_from_user,
    parse_domain_insert,
    parse_domain_update,
)


def api_jumperurl_gencode(length=32):
    code = False
    while code == False:
        code = secrets.token_urlsafe(length)
        with app.app_context():
            found = list(
                r.table("domains").get_all(code, index="jumperurl").run(db.conn)
            )
        if len(found) == 0:
            return code
    raise Error(
        "internal_server",
        "Unable to create jumperurl code",
        traceback.format_exc(),
    )


class ApiDesktopsPersistent:
    def __init__(self):
        None

    def Delete(self, desktop_id):
        with app.app_context():
            desktop = r.table("domains").get(desktop_id).run(db.conn)
        if desktop == None:
            raise Error("not_found", "Desktop not found", traceback.format_exc())
        ds.delete_desktop(desktop_id, desktop["status"])
        with app.app_context():
            r.table("bookings").get_all(
                ["desktop", desktop_id], index="item_type-id"
            ).delete().run(db.conn)

    def Get(self, desktop_id):
        with app.app_context():
            desktop = r.table("domains").get(desktop_id).run(db.conn)
            if not desktop:
                raise Error("not_found", "Desktop not found", traceback.format_exc())
            return desktop

    def NewFromTemplate(
        self,
        desktop_name,
        desktop_description,
        template_id,
        user_id,
        deployment_tag_dict=False,
        new_data=None,
        image=None,
    ):
        with app.app_context():
            template = r.table("domains").get(template_id).run(db.conn)
            if not template:
                raise Error("not_found", "Template not found", traceback.format_exc())
            user = r.table("users").get(user_id).run(db.conn)
            if not user:
                raise Error("not_found", "NewFromTemplate: user id not found.")
            group = r.table("groups").get(user["group"]).run(db.conn)
            if not group:
                raise Error("not_found", "NewFromTemplate: group id not found.")

        parsed_name = _parse_string(desktop_name)
        new_desktop_id = "_" + user_id + "-" + parsed_name
        with app.app_context():
            if r.table("domains").get(new_desktop_id).run(db.conn):
                raise Error(
                    "conflict",
                    "NewFromTemplate: user already has a desktop with the same id.",
                )

        if new_data:
            template["create_dict"]["hardware"] = {
                **template["create_dict"]["hardware"],
                **parse_domain_insert(new_data)["hardware"],
            }
            template["create_dict"]["reservables"] = new_data["hardware"]["reservables"]
            template["create_dict"]["hardware"].pop("reservables")
        else:
            template["create_dict"]["hardware"]["memory"] = (
                template["create_dict"]["hardware"]["memory"] / 1048576
            )

        parent_disk = template["hardware"]["disks"][0]["file"]
        create_dict = template["create_dict"]
        create_dict["hardware"]["disks"] = [
            {"extension": "qcow2", "parent": parent_disk}
        ]
        try:
            create_dict = _parse_media_info(create_dict)
        except:
            raise Error(
                "internal_server", "NewFromTemplate: unable to parse media info."
            )

        if "interfaces_mac" in create_dict["hardware"].keys():
            create_dict["hardware"].pop("interfaces_mac")

        if not deployment_tag_dict:
            payload = gen_payload_from_user(user)
            create_dict = quotas.limit_user_hardware_allowed(payload, create_dict)
        new_desktop = {
            "id": new_desktop_id,
            "name": desktop_name,
            "description": desktop_description,
            "kind": "desktop",
            "user": user_id,
            "username": user["username"],
            "status": "Creating",
            "detail": None,
            "category": user["category"],
            "group": user["group"],
            "xml": None,
            "icon": template["icon"],
            "image": template["image"],
            "server": template["server"],
            "os": template["os"],
            "guest_properties": new_data.get("guest_properties")
            if new_data
            else template["guest_properties"],
            "create_dict": {
                "hardware": create_dict["hardware"],
                "origin": template["id"],
            },
            "hypervisors_pools": template["hypervisors_pools"],
            "allowed": {
                "roles": False,
                "categories": False,
                "groups": False,
                "users": False,
            },
            "accessed": time.time(),
            "persistent": True,
            "forced_hyp": False,
            "from_template": template["id"],
        }
        if deployment_tag_dict:
            new_desktop = {**new_desktop, **deployment_tag_dict}

        new_desktop["create_dict"]["hardware"]["memory"] = (
            int(new_data["hardware"]["memory"] * 1048576)
            if new_data and new_data.get("hardware", {}).get("memory")
            else int(template["create_dict"]["hardware"]["memory"] * 1048576)
        )

        if create_dict.get("reservables"):
            new_desktop["create_dict"] = {
                **new_desktop["create_dict"],
                **{"reservables": create_dict["reservables"]},
            }

        with app.app_context():
            if (
                _check(r.table("domains").insert(new_desktop).run(db.conn), "inserted")
                == False
            ):
                raise Error(
                    "internal_server",
                    "NewFromTemplate: unable to insert new desktop in database",
                )
            else:
                if image:
                    image_data = image
                    if not image_data.get("file"):
                        img_uuid = api_cards.update(
                            new_desktop_id, image_data["id"], image_data["type"]
                        )
                        card = api_cards.get_card(img_uuid, image_data["type"])
                    else:
                        img_uuid = api_cards.upload(new_desktop_id, image_data)
                        card = api_cards.get_card(img_uuid, image_data["type"])
                return new_desktop_id

    def BulkDesktops(self, payload, data):
        selected = data["allowed"]
        users = []

        if payload["role_id"] == "admin":
            if selected["roles"] is not False:
                if not selected["roles"]:
                    with app.app_context():
                        selected["roles"] = [
                            r["id"]
                            for r in list(r.table("roles").pluck("id").run(db.conn))
                        ]
                for role in selected["roles"]:
                    # Can't use get_all as has no index in database
                    with app.app_context():
                        roles = list(
                            r.table("users")
                            .filter({"role": role})
                            .pluck("id")
                            .run(db.conn)
                        )
                    users = users + [r["id"] for r in roles]

            if selected["categories"] is not False:
                if not selected["categories"]:
                    with app.app_context():
                        selected["categories"] = [
                            c["id"]
                            for c in list(
                                r.table("categories").pluck("id").run(db.conn)
                            )
                        ]
                with app.app_context():
                    categories = list(
                        r.table("users")
                        .get_all(r.args(selected["categories"]), index="category")
                        .pluck("id")
                        .run(db.conn)
                    )
                users = users + [c["id"] for c in categories]

        if selected["groups"] is not False:
            if not selected["groups"]:
                query = r.table("groups")
                if payload["role_id"] == "manager":
                    query = query.get_all(
                        payload["category_id"], index="parent_category"
                    )
                with app.app_context():
                    selected["groups"] = [
                        g["id"] for g in list(query.pluck("id").run(db.conn))
                    ]
            with app.app_context():
                groups = list(
                    r.table("users")
                    .get_all(r.args(selected["groups"]), index="group")
                    .pluck("id")
                    .run(db.conn)
                )
            users = users + [g["id"] for g in groups]

        if selected["users"] is not False:
            if not selected["users"]:
                query = r.table("users")
                if payload["role_id"] == "manager":
                    query = query.get_all(payload["category_id"], index="category")
                with app.app_context():
                    selected["users"] = [
                        u["id"] for u in list(query.pluck("id").run(db.conn))
                    ]
            users = users + selected["users"]

        users = list(set(users))
        for user_id in users:
            check_user_duplicated_domain_name("", data["name"], user_id)
            quotas.DesktopCreate(user_id)

        for user_id in users:
            self.NewFromTemplate(
                data["name"], data["description"], data["template_id"], user_id
            )

    def NewFromMedia(self, payload, data):
        with app.app_context():
            user = r.table("users").get(payload["user_id"]).run(db.conn)

        with app.app_context():
            if r.table("domains").get(data["id"]).run(db.conn):
                raise Error(
                    "conflict",
                    "Already exists a desktop with this id",
                    traceback.format_exc(),
                )
        with app.app_context():
            xml = r.table("virt_install").get(data["xml_id"]).run(db.conn)
            if not xml:
                raise Error(
                    "not_found", "Not found virt install xml id", traceback.format_exc()
                )
        with app.app_context():
            media = r.table("media").get(data["media_id"]).run(db.conn)
            if not media:
                raise Error("not_found", "Not found media id", traceback.format_exc())

        with app.app_context():
            graphics = [
                g["id"]
                for g in r.table("graphics")
                .get_all(r.args(data["hardware"]["graphics"]))
                .run(db.conn)
            ]
            if not len(graphics):
                raise Error(
                    "not_found", "Not found graphics ids", traceback.format_exc()
                )

        with app.app_context():
            videos = [
                v["id"]
                for v in r.table("videos")
                .get_all(r.args(data["hardware"]["videos"]))
                .run(db.conn)
            ]
            if not len(videos):
                raise Error("not_found", "Not found videos ids", traceback.format_exc())

        with app.app_context():
            interfaces = [
                i["id"]
                for i in r.table("interfaces")
                .get_all(r.args(data["hardware"]["interfaces"]))
                .run(db.conn)
            ]
            if not len(interfaces):
                raise Error(
                    "not_found", "Not found interface id", traceback.format_exc()
                )

        if data["hardware"].get("disk_size"):
            disks = [
                {
                    "bus": data["hardware"]["disk_bus"],
                    "extension": "qcow2",
                    "size": str(data["hardware"]["disk_size"]) + "G",
                }
            ]
        else:
            disks = []

        domain = {
            "id": data["id"],
            "name": data["name"],
            "description": data["description"],
            "kind": "desktop",
            "status": "CreatingDiskFromScratch",
            "detail": "Creating desktop from existing disk and checking if it is valid (can start)",
            "user": payload["user_id"],
            "username": user["username"],
            "category": payload["category_id"],
            "group": payload["group_id"],
            "server": data["server"],
            "xml": None,
            "icon": "fa-circle-o"
            if data["kind"] == "iso"
            else "fa-disk-o"
            if data["kind"] == "file"
            else "fa-floppy-o",
            "image": get_domain_stock_card(data["id"]),
            "os": "win",
            "guest_properties": data.get(
                "guest_properties", default_guest_properties()
            ),
            "hypervisors_pools": ["default"],
            "accessed": time.time(),
            "persistent": True,
            "forced_hyp": data["forced_hyp"],
            "allowed": {
                "categories": False,
                "groups": False,
                "roles": False,
                "users": False,
            },
            "create_dict": {
                "create_from_virt_install_xml": xml["id"],
                "hardware": {
                    "disks": disks,
                    "disk_bus": data["hardware"]["disk_bus"],
                    "isos": [{"id": media["id"]}],
                    "floppies": [],
                    "boot_order": data["hardware"]["boot_order"],
                    "graphics": graphics,
                    "videos": videos,
                    "interfaces": interfaces,
                    "memory": int(data["hardware"]["memory"]),
                    "vcpus": int(data["hardware"]["vcpus"]),
                },
            },
        }

        res = qp.limit_user_hardware_allowed(payload, domain["create_dict"])
        if res["limited_hardware"]:
            raise Error(
                "bad_request",
                "Unauthorized hardware items: " + str(res["limited_hardware"]),
                traceback.format_exc(),
            )
        domain["create_dict"]["hardware"]["memory"] = int(
            data["hardware"]["memory"] * 1048576
        )
        with app.app_context():
            r.table("domains").insert(domain).run(db.conn)
        return domain["id"]

    def UserDesktop(self, desktop_id):
        try:
            with app.app_context():
                return (
                    r.table("domains")
                    .get(desktop_id)
                    .pluck("user")
                    .run(db.conn)["user"]
                )
        except:
            raise Error("not_found", "Desktop not found", traceback.format_exc())

    def Start(self, desktop_id):
        with app.app_context():
            desktop = r.table("domains").get(desktop_id).run(db.conn)
        if not desktop:
            raise Error("not_found", "Desktop not found", traceback.format_exc())
        if desktop["status"] == "Started":
            return desktop_id
        if desktop["status"] not in ["Stopped", "Failed"]:
            raise Error(
                "precondition_required",
                "Desktop can't be started from " + str(desktop["status"]),
                traceback.format_exc(),
            )

        # Start the domain
        ds.WaitStatus(desktop_id, "Any", "Starting", "Started")
        return desktop_id

    def Stop(self, desktop_id):
        with app.app_context():
            desktop = r.table("domains").get(desktop_id).run(db.conn)
        if not desktop:
            raise Error("not_found", "Desktop not found", traceback.format_exc())
        if desktop["status"] == "Stopped":
            return desktop_id
        if desktop["status"] not in ["Started", "Shutting-down"]:
            raise Error(
                "precondition_required",
                "Desktop can't be stopped from " + str(desktop["status"]),
                traceback.format_exc(),
            )

        # Stop the domain
        if desktop["status"] == "Started":
            ds.WaitStatus(
                desktop_id, desktop["status"], "Shutting-down", "Shutting-down"
            )

        if desktop["status"] == "Shutting-down":
            ds.WaitStatus(desktop_id, desktop["status"], "Stopping", "Stopped")

        return desktop_id

    def Update(self, desktop_id, desktop_data, admin_or_manager=False):
        if desktop_data.get("image"):
            image_data = desktop_data.pop("image")

            if not image_data.get("file"):
                img_uuid = api_cards.update(
                    desktop_id, image_data["id"], image_data["type"]
                )
                card = api_cards.get_card(img_uuid, image_data["type"])
            else:
                img_uuid = api_cards.upload(desktop_id, image_data)
                card = api_cards.get_card(img_uuid, image_data["type"])

        desktop = parse_domain_update(desktop_id, desktop_data, admin_or_manager)
        with app.app_context():
            if not _check(
                r.table("domains").get(desktop_id).update(desktop).run(db.conn),
                "replaced",
            ):
                raise Error(
                    "internal_server",
                    "Unable to update desktop in database",
                    traceback.format_exc(),
                )

    def JumperUrl(self, id):
        with app.app_context():
            domain = r.table("domains").get(id).run(db.conn)
        if domain == None:
            raise Error(
                "not_found",
                "Could not get domain jumperurl as domain not exists",
                traceback.format_exc(),
            )
        if "jumperurl" not in domain.keys():
            return {"jumperurl": False}
        return {"jumperurl": domain["jumperurl"]}

    def JumperUrlReset(self, id, disabled=False, length=32):
        if disabled == True:
            with app.app_context():
                try:
                    r.table("domains").get(id).update({"jumperurl": False}).run(db.conn)
                except:
                    raise Error(
                        "not_found",
                        "Unable to reset jumperurl as domain not exists",
                        traceback.format_exc(),
                    )
        else:
            code = api_jumperurl_gencode()
            with app.app_context():
                r.table("domains").get(id).update({"jumperurl": code}).run(db.conn)
            return code
