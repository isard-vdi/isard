#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import traceback

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import traceback

from ..libv2.api_admin import admin_table_delete, admin_table_update
from ..libv2.api_desktops_persistent import ApiDesktopsPersistent
from .api_exceptions import Error
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

persistent = ApiDesktopsPersistent()


class ApiMedia:
    def __init__(self):
        None

    def List(self, id):
        with app.app_context():
            domain_cd = (
                r.table("domains")
                .get(id)
                .pluck({"create_dict": {"hardware"}})
                .run(db.conn)["create_dict"]["hardware"]
            )
        media = []
        if "isos" in domain_cd and domain_cd["isos"] != []:
            for m in domain_cd["isos"]:
                try:
                    iso = (
                        r.table("media")
                        .get(m["id"])
                        .pluck("id", "name", {"progress": "total"})
                        .merge({"kind": "iso"})
                        .run(db.conn)
                    )
                    iso["size"] = iso.pop("progress")["total"]
                    media.append(iso)
                except:
                    """Media does not exist"""
                    None
        if "floppies" in domain_cd and domain_cd["floppies"] != []:
            for m in domain_cd["floppies"]:
                try:
                    fd = (
                        r.table("media")
                        .get(m["id"])
                        .pluck("id", "name", {"progress": "total"})
                        .merge({"kind": "fd"})
                        .run(db.conn)
                    )
                    fd["size"] = fd.pop("progress")["total"]
                    media.append(fd)
                except:
                    """Media does not exist"""
                    None
        return media

    def Get(self, media_id):
        with app.app_context():
            media = r.table("media").get(media_id).run(db.conn)
        if not media:
            raise Error(
                "not_found",
                "Not found media: " + media_id,
                traceback.format_exc(),
            )
        return media

    def DesktopList(self, media_id):
        with app.app_context():
            desktops = list(
                r.table("domains")
                .filter(
                    lambda dom: dom["create_dict"]["hardware"]["isos"].contains(
                        lambda media: media["id"].eq(media_id)
                    )
                )
                .pluck(
                    "id",
                    "name",
                    "kind",
                    "status",
                    "user",
                    {"create_dict": {"hardware": {"isos"}}},
                )
                .run(db.conn)
            )
        return desktops

    def DeleteDesktops(self, media_id):
        for desktop in self.DesktopList(media_id):
            if desktop["status"] in ["Starting", "Started", "Shutting-down"]:
                persistent.Stop(desktop["id"])
        # If was left in Shutting-down and did not shut down, force it.
        for desktop in self.DesktopList(media_id):
            if desktop["status"] in ["Starting", "Started", "Shutting-down"]:
                persistent.Stop(desktop["id"])

        for desktop in self.DesktopList(media_id):
            desktop["create_dict"]["hardware"]["isos"][:] = [
                iso
                for iso in desktop["create_dict"]["hardware"]["isos"]
                if iso.get("id") != media_id
            ]

            desktop.pop("name", None)
            desktop.pop("kind", None)
            desktop["status"] = "Updating"

            admin_table_update("domains", desktop)
        admin_table_update("media", {"id": media_id, "status": "Deleting"})
