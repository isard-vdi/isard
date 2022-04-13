#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import pprint
import time
from datetime import datetime, timedelta

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from rethinkdb.errors import ReqlTimeoutError

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from .apiv2_exc import *
from .ds import DS

ds = DS()

from .helpers import _check, _disk_path, _parse_media_info, _parse_string


class ApiTemplates:
    def __init__(self):
        None

    def New(
        self,
        template_name,
        desktop_id,
        allowed_roles=False,
        allowed_categories=False,
        allowed_groups=False,
        allowed_users=False,
    ):

        allowed = {
            "roles": allowed_roles,
            "categories": allowed_categories,
            "groups": allowed_groups,
            "users": allowed_users,
        }

        parsed_name = _parse_string(template_name)
        user_id = desktop_id.split("_")[1]
        template_id = "_" + user_id + "-" + parsed_name

        with app.app_context():
            try:
                user = (
                    r.table("users")
                    .get(user_id)
                    .pluck("id", "category", "group", "provider", "username", "uid")
                    .run(db.conn)
                )
            except:
                raise UserNotFound
            desktop = r.table("domains").get(desktop_id).run(db.conn)
            if desktop == None:
                raise DesktopNotFound

        parent_disk = desktop["hardware"]["disks"][0]["file"]

        hardware = desktop["create_dict"]["hardware"]

        dir_disk, disk_filename = _disk_path(user, parsed_name)
        hardware["disks"] = [
            {"file": dir_disk + "/" + disk_filename, "parent": parent_disk}
        ]

        create_dict = _parse_media_info({"hardware": hardware})
        create_dict["origin"] = desktop_id

        template_dict = {
            "id": template_id,
            "name": template_name,
            "description": "Api created",
            "kind": "template",
            "user": user["id"],
            "username": user["username"],
            "status": "CreatingTemplate",
            "detail": None,
            "category": user["category"],
            "group": user["group"],
            "xml": desktop["xml"],  #### In desktop creation is
            "icon": desktop["icon"],
            "server": desktop["server"],
            "os": desktop["os"],
            "options": desktop["options"],
            "create_dict": create_dict,
            "hypervisors_pools": ["default"],
            "parents": desktop["parents"] if "parents" in desktop.keys() else [],
            "allowed": allowed,
        }

        with app.app_context():
            if r.table("domains").get(template_dict["id"]).run(db.conn) == None:

                if (
                    _check(
                        r.table("domains")
                        .get(desktop_id)
                        .update(
                            {
                                "create_dict": {"template_dict": template_dict},
                                "status": "CreatingTemplate",
                            }
                        )
                        .run(db.conn),
                        "replaced",
                    )
                    == False
                ):
                    raise NewTemplateNotInserted
                else:
                    return template_dict["id"]
            else:
                raise TemplateExists

    def Get(self, template_id):
        with app.app_context():
            try:
                return (
                    r.table("domains")
                    .get(template_id)
                    .pluck("id", "name", "icon", "image", "description")
                    .run(db.conn)
                )
            except:
                raise UserTemplatesError

    def Delete(self, template_id):
        ## TODO: Delete all related desktops!!!
        ds.delete_desktop(template_id, "Stopped")

    # Disable or enable template
    def UpdateTemplate(self, template_id, data):
        with app.app_context():
            template = r.table("domains").get(template_id).run(db.conn)
        if template and template["kind"] == "template":
            with app.app_context():
                r.table("domains").get(template_id).update(data).run(db.conn)
            return True
        return False
