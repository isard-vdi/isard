#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import time
import traceback

from api._common.domain import Domain
from rethinkdb import RethinkDB

from api import app

from ..libv2.validators import _validate_item
from .api_cards import ApiCards

r = RethinkDB()
import logging as log

from .._common.api_exceptions import Error
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from .ds import DS

ds = DS()

from .helpers import _check, _parse_media_info, _parse_string, get_user_data


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
                raise Error(
                    "not_found",
                    "User not found",
                    traceback.format_exc(),
                    description_code="not_found",
                )
            desktop = r.table("domains").get(desktop_id).run(db.conn)
            if desktop == None:
                raise Error(
                    "not_found",
                    "Desktop not found",
                    traceback.format_exc(),
                    description_code="not_found",
                )
            if desktop.get("status") != "Stopped":
                raise Error(
                    "precondition_required",
                    "To create a template, status desktop must be Stopped",
                    traceback.format_exc(),
                )
            if desktop.get("server"):
                raise Error(
                    "internal_server",
                    "Can't create a template from a server",
                    traceback.format_exc(),
                )
        if not Domain(desktop.get("id")).storage_ready:
            raise Error(
                error="precondition_required",
                description="Desktop storages are not ready",
                description_code="desktop_storage_not_ready",
            )

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
            "accessed": int(time.time()),
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
            "os": desktop["os"],
            "guest_properties": desktop["guest_properties"],
            "create_dict": create_dict,
            "hypervisors_pools": ["default"],
            "parents": desktop["parents"] if "parents" in desktop.keys() else [],
            "allowed": allowed,
            "enabled": enabled,
            "tag": False,
            "tag_name": False,
            "tag_visible": False,
            "favourite_hyp": desktop.get("favourite_hyp", False),
            "forced_hyp": desktop.get("forced_hyp", False),
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
                        "Unable to update new template into database.",
                        description_code="unable_to_update",
                    )
                else:
                    return template_id
            else:
                raise Error(
                    "conflict",
                    "Template id already exists: " + str(template_id),
                    description_code="template_already_exists" + str(template_id),
                )

    def Duplicate(
        self,
        payload,
        template_id,
        name,
        allowed={"roles": False, "categories": False, "groups": False, "users": False},
        description="",
        enabled=False,
    ):
        with app.app_context():
            template = (
                r.table("domains")
                .get(template_id)
                .without("id", "history_domain")
                .run(db.conn)
            )
        if not template:
            raise Error(
                "not_found",
                "Template id not found",
                traceback.format_exc(),
                description_code="not_found",
            )

        template = {**template, **get_user_data(payload["user_id"])}
        template["name"] = name
        template["description"] = description
        template["allowed"] = allowed
        template["enabled"] = enabled
        template["status"] = "Stopped"
        template["accessed"] = int(time.time())
        template["parents"] = []
        template["duplicate_parent_template"] = template.get(
            "duplicate_parent_template", template_id
        )

        _validate_item("template", template)
        try:
            with app.app_context():
                new_template_id = (
                    r.table("domains")
                    .insert(template, return_changes=True)["changes"]["new_val"]["id"]
                    .run(db.conn)
                )
        except:
            raise Error(
                "internal_server",
                "Unable to insert duplicate template",
                traceback.format_exc(),
            )
        ds._wait_for_domain_status(new_template_id, "Stopped", "Updating", "Stopped")
        return new_template_id

    def Get(self, template_id):
        with app.app_context():
            try:
                return (
                    r.table("domains")
                    .get(template_id)
                    .pluck(
                        "id",
                        "name",
                        "icon",
                        "image",
                        "description",
                        "allowed",
                        "guest_properties",
                        "create_dict",
                        "status",
                    )
                    .run(db.conn)
                )
            except:
                raise Error(
                    "not_found", "Template id not found", traceback.format_exc()
                )

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
                description_code="not_found",
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
            description_code="unable_to_update",
        )

    def count(seld, user_id):
        return (
            r.table("domains")
            .get_all(["template", user_id], index="kind_user")
            .count()
            .run(db.conn)
        )
