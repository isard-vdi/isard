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

from ..libv2.api_hypervisors import (
    check_create_storage_pool_availability,
    check_virt_storage_pool_availability,
)
from ..libv2.api_scheduler import Scheduler
from ..libv2.quotas import Quotas
from .api_desktop_events import desktop_start
from .api_nonpersistentdesktop_events import (
    desktop_non_persistent_delete,
    desktops_non_persistent_delete,
)

quotas = Quotas()
from isardvdi_common.api_exceptions import Error

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..libv2.isardViewer import isardViewer
from .validators import _validate_item

isardviewer = isardViewer()
scheduler = Scheduler()

from .helpers import (
    _check,
    _parse_media_info,
    gen_payload_from_user,
    parse_domain_insert,
)


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
            check_virt_storage_pool_availability(desktops[0]["id"])
            desktop_start(desktops[0]["id"], wait_seconds=1)
            scheduler.add_desktop_timeouts(
                gen_payload_from_user(user_id), desktops[0]["id"]
            )
            return desktops[0]["id"]

        # If not, delete all nonpersistent desktops based on this template from user
        desktops_non_persistent_delete(user_id, template_id)

        # and get a new nonpersistent desktops from this template
        return self._nonpersistent_desktop_create_and_start(user_id, template_id)

    def Delete(self, desktop_id):
        desktop_non_persistent_delete(desktop_id)

    def _nonpersistent_desktop_create_and_start(self, user_id, template_id):
        with app.app_context():
            user = r.table("users").get(user_id).run(db.conn)
        if user == None:
            raise Error("not_found", "User not found", traceback.format_exc())
        check_create_storage_pool_availability(user.get("category_id"))
        # Create the domain from that template
        desktop_id = self._nonpersistent_desktop_from_tmpl(user_id, template_id)

        # Disk is created by engine and not ready yet, thus commented this check
        # check_virt_storage_pool_availability(desktop_id)
        desktop_start(desktop_id)
        payload = gen_payload_from_user(user_id)
        scheduler.add_desktop_timeouts(payload, desktop_id)
        return desktop_id

    def _nonpersistent_desktop_from_tmpl(self, user_id, template_id):
        with app.app_context():
            template = r.table("domains").get(template_id).run(db.conn)
        if not template:
            raise Error("not_found", "Template not found", traceback.format_exc())
        with app.app_context():
            user = r.table("users").get(user_id).run(db.conn)
        if not user:
            raise Error("not_found", "NewNonPersistent: user id not found.")
        with app.app_context():
            group = r.table("groups").get(user["group"]).run(db.conn)
        if not group:
            raise Error("not_found", "NewNonPersistent: group id not found.")

        parent_disk = template["hardware"]["disks"][0]["file"]

        create_dict = template["create_dict"]
        create_dict["hardware"]["disks"] = [
            {"extension": "qcow2", "parent": parent_disk}
        ]
        create_dict = _parse_media_info(create_dict)

        template["create_dict"]["hardware"]["interfaces"] = [
            i["id"] for i in template["create_dict"]["hardware"]["interfaces"]
        ]

        create_dict["hardware"] = {
            **template["create_dict"]["hardware"],
            **parse_domain_insert(template["create_dict"])["hardware"],
        }

        if create_dict.get("reservables", {}).get("vgpus"):
            raise Error(
                "bad_request",
                "Can't create temporal desktop from a template with a reservable",
                traceback.format_exc(),
                "temporal_new_reservable",
            )

        new_desktop = {
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
            "accessed": int(time.time()),
            "persistent": False,
            "from_template": template["id"],
        }

        new_desktop = _validate_item("domains", new_desktop)

        with app.app_context():
            if _check(r.table("domains").insert(new_desktop).run(db.conn), "inserted"):
                return new_desktop["id"]
        raise Error(
            "internal_server",
            "Unable to create non persistent desktop",
            traceback.format_exc(),
        )
