#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import time

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log
import traceback

from .api_exceptions import Error
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..libv2.isardViewer import isardViewer

isardviewer = isardViewer()

from .ds import DS

ds = DS()

from .helpers import _check, _parse_media_info, _parse_string


class ApiDesktopsNonPersistent:
    def __init__(self):
        None

    def New(self, user_id, template_id):
        with app.app_context():
            if r.table("users").get(user_id).run(db.conn) is None:
                raise Error("not_found", "User not found", traceback.format_exc())
        # Has a desktop with this template? Then return it (start it if stopped)
        with app.app_context():
            desktops = list(
                r.db("isard")
                .table("domains")
                .get_all(user_id, index="user")
                .filter({"from_template": template_id, "persistent": False})
                .run(db.conn)
            )
        if len(desktops) == 1:
            if desktops[0]["status"] == "Started":
                return desktops[0]["id"]
            elif desktops[0]["status"] == "Stopped":
                ds.WaitStatus(desktops[0]["id"], "Stopped", "Starting", "Started")
                return desktops[0]["id"]

        # If not, delete all nonpersistent desktops based on this template from user
        ds.delete_non_persistent(user_id, template_id)

        # and get a new nonpersistent desktops from this template
        return self._nonpersistent_desktop_create_and_start(user_id, template_id)

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

    def DeleteOthers(self, user_id, template_id):
        """Will leave only one nonpersistent desktops form template `template_id`

        :param user_id: User ID
        :param template_id: Template ID
        :return: None
        """
        with app.app_context():
            if r.table("users").get(user_id).run(db.conn) is None:
                raise Error("not_found", "User not found", traceback.format_exc())

        ####### Get how many desktops are from this template and leave only one
        with app.app_context():
            desktops = list(
                r.db("isard")
                .table("domains")
                .get_all(["desktop", user_id], index="kind_user")
                .filter(
                    {
                        "from_template": template_id,
                        "persistent": False,
                    }
                )
                .order_by(r.desc("accessed"))
                .run(db.conn)
            )
        # This situation should not happen as there should only be a maximum of 1 non persistent desktop
        # So we delete all but the first one [0] as the descendant order_by lets this as the newer desktop
        if len(desktops) > 1:
            for i in range(1, len(desktops) - 1):
                ## We delete all and return the first as the order is descendant (first is the newer desktop)
                ds.delete_desktop(desktops[i]["id"])

    def _nonpersistent_desktop_create_and_start(self, user_id, template_id):
        with app.app_context():
            user = r.table("users").get(user_id).run(db.conn)
        if user == None:
            raise Error("not_found", "User not found", traceback.format_exc())
        # Create the domain from that template
        desktop_id = self._nonpersistent_desktop_from_tmpl(user_id, template_id)

        ds.WaitStatus(desktop_id, "Any", "Any", "Started")
        return desktop_id

    def _nonpersistent_desktop_from_tmpl(self, user_id, template_id):
        with app.app_context():
            template = r.table("domains").get(template_id).run(db.conn)
            if not template:
                raise Error("not_found", "Template not found", traceback.format_exc())
            user = r.table("users").get(user_id).run(db.conn)
            if not user:
                raise Error("not_found", "NewNonPersistent: user id not found.")
            group = r.table("groups").get(user["group"]).run(db.conn)
            if not group:
                raise Error("not_found", "NewNonPersistent: group id not found.")

        timestamp = time.strftime("%Y%m%d%H%M%S")
        parsed_name = (timestamp + "-" + _parse_string(template["name"]))[:40]

        parent_disk = template["hardware"]["disks"][0]["file"]

        create_dict = template["create_dict"]
        create_dict["hardware"]["disks"] = [
            {"extension": "qcow2", "parent": parent_disk}
        ]
        create_dict = _parse_media_info(create_dict)

        if "interfaces_mac" in create_dict["hardware"].keys():
            create_dict["hardware"].pop("interfaces_mac")

        new_desktop = {
            "id": "_" + user_id + "-" + parsed_name,
            "name": template["name"],
            "description": template["description"],
            "kind": "desktop",
            "user": user_id,
            "username": user["username"],
            "status": "CreatingAndStarting",
            "detail": None,
            "category": user["category"],
            "group": user["group"],
            "xml": None,
            "icon": template["icon"],
            "image": template["image"],
            "server": False,
            "os": template["os"],
            "guest_properties": template["guest_properties"],
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
            "persistent": False,
            "from_template": template["id"],
        }

        with app.app_context():
            if _check(r.table("domains").insert(new_desktop).run(db.conn), "inserted"):
                return new_desktop["id"]
        raise Error(
            "internal_server",
            "Unable to create non persistent desktop",
            traceback.format_exc(),
        )

    def DesktopStart(self, desktop_id):
        ds.WaitStatus(desktop_id, "Any", "Any", "Started")
