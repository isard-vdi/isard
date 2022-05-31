#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import traceback

from rethinkdb import RethinkDB

from api import app

from .api_cards import ApiCards

r = RethinkDB()
import logging as log

from .api_exceptions import Error
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from .ds import DS

ds = DS()

from .helpers import _check, _parse_media_info, _parse_string


class ApiTemplates:
    def __init__(self):
        None

    def New(
        self,
        user_id,
        template_id,
        name,
        desktop_id,
        allowed={"roles": False, "categories": False, "groups": False, "users": False},
        description="",
        enabled=False,
    ):

        parsed_name = _parse_string(name)

        with app.app_context():
            try:
                user = (
                    r.table("users")
                    .get(user_id)
                    .pluck("id", "category", "group", "provider", "username", "uid")
                    .run(db.conn)
                )
            except:
                raise Error("not_found", "User not found", traceback.format_exc())
            desktop = r.table("domains").get(desktop_id).run(db.conn)
            if desktop == None:
                raise Error("not_found", "Desktop not found", traceback.format_exc())

        parent_disk = desktop["hardware"]["disks"][0]["file"]

        hardware = desktop["create_dict"]["hardware"]
        hardware["disks"] = [{"extension": "qcow2", "parent": parent_disk}]

        create_dict = _parse_media_info({"hardware": hardware})
        create_dict["origin"] = desktop_id

        if desktop["create_dict"].get("reservables"):
            create_dict = {
                **create_dict,
                **{"reservables": desktop["create_dict"]["reservables"]},
            }

        template_dict = {
            "id": template_id,
            "name": name,
            "description": description,
            "kind": "template",
            "user": user["id"],
            "username": user["username"],
            "status": "CreatingTemplate",
            "detail": None,
            "category": user["category"],
            "group": user["group"],
            "xml": desktop["xml"],  #### In desktop creation is
            "icon": desktop["icon"],
            "image": ApiCards().get_domain_stock_card(template_id),
            "server": desktop["server"],
            "os": desktop["os"],
            "guest_properties": desktop["guest_properties"],
            "create_dict": create_dict,
            "hypervisors_pools": ["default"],
            "parents": desktop["parents"] if "parents" in desktop.keys() else [],
            "allowed": allowed,
            "enabled": enabled,
        }

        with app.app_context():
            if r.table("domains").get(template_id).run(db.conn) == None:
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
                    raise Error(
                        "internal_server",
                        "Unable to update at new template into database.",
                    )
                else:
                    return template_id
            else:
                raise Error(
                    "conflict", "Template id already exists: " + str(template_id)
                )

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
        if not template:
            raise Error(
                "not_found",
                "Unable to update inexistent template",
                traceback.format_exc(),
            )
        if template and template["kind"] == "template":
            with app.app_context():
                r.table("domains").get(template_id).update(data).run(db.conn)
            template = r.table("domains").get(template_id).run(db.conn)
            return template
        raise Error(
            "conflict",
            "Unable to update enable in a non template kind domain",
            traceback.format_exc(),
        )
