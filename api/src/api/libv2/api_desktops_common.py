#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import time
import traceback

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..libv2.api_scheduler import Scheduler
from ..libv2.helpers import gen_payload_from_user
from .api_desktop_events import desktop_start
from .api_exceptions import Error
from .isardViewer import isardViewer, viewer_jwt

isardviewer = isardViewer()

from .ds import DS

ds = DS()
scheduler = Scheduler()

import secrets


class ApiDesktopsCommon:
    def __init__(self):
        None

    def DesktopViewer(self, desktop_id, protocol, get_cookie=False):
        if protocol in ["url", "file"]:
            direct_protocol = protocol
            protocol = "browser-vnc"
        else:
            direct_protocol = False

        viewer_txt = isardviewer.viewer_data(
            desktop_id, protocol=protocol, get_cookie=get_cookie
        )

        with app.app_context():
            r.table("domains").get(desktop_id).update(
                {"accessed": int(time.time())}
            ).run(db.conn)

        if not direct_protocol:
            return viewer_txt
        else:
            return self.DesktopDirectViewer(desktop_id, viewer_txt, direct_protocol)

    def DesktopViewerFromToken(self, token, start_desktop=True):
        with app.app_context():
            domains = list(
                r.table("domains").get_all(token, index="jumperurl").run(db.conn)
            )
        domains = [
            d
            for d in domains
            if not d.get("tag") or d.get("tag") and d.get("tag_visible")
        ]
        if len(domains) == 0:
            raise Error(
                "not_found",
                "Desktop not found",
                traceback.format_exc(),
                description_code="not_found",
            )
        if len(domains) == 1:
            scheduled = False
            if start_desktop and domains[0]["status"] == "Stopped":
                desktop_start(domains[0]["id"], wait_seconds=60)
                payload = gen_payload_from_user(domains[0]["user"])
                scheduled = scheduler.add_desktop_timeouts(payload, domains[0]["id"])
            viewers = {
                "desktopId": domains[0]["id"],
                "jwt": viewer_jwt(domains[0]["id"], minutes=30),
                "vmName": domains[0]["name"],
                "vmDescription": domains[0]["description"],
                "vmState": "Started",
                "scheduled": scheduled if scheduled else domains[0].get("scheduled"),
            }
            desktop_viewers = list(domains[0]["guest_properties"]["viewers"].keys())
            if "file_spice" in desktop_viewers:
                viewers["file-spice"] = self.DesktopViewer(
                    domains[0]["id"], protocol="file-spice", get_cookie=True
                )
            if "browser_vnc" in desktop_viewers:
                viewers["browser-vnc"] = self.DesktopViewer(
                    domains[0]["id"], protocol="browser-vnc", get_cookie=True
                )
            if "browser_rdp" in desktop_viewers:
                if domains[0].get("viewer", True) == False:
                    viewers["browser_rdp"] = {"kind": "browser", "protocol": "rdp"}
                    viewers["vmState"] = "WaitingIP"
                elif not domains[0].get("viewer", {}).get("guest_ip"):
                    viewers["browser_rdp"] = {"kind": "browser", "protocol": "rdp"}
                    viewers["vmState"] = "WaitingIP"
                else:
                    viewers["browser-rdp"] = self.DesktopViewer(
                        domains[0]["id"],
                        protocol="browser-rdp",
                        get_cookie=True,
                    )
            if "file_rdpgw" in desktop_viewers:
                if domains[0].get("viewer", True) == False:
                    viewers["file-rdpgw"] = {"kind": "file", "protocol": "rdpgw"}
                    viewers["vmState"] = "WaitingIP"
                elif not domains[0].get("viewer", {}).get("guest_ip"):
                    viewers["file-rdpgw"] = {"kind": "file", "protocol": "rdpgw"}
                    viewers["vmState"] = "WaitingIP"
                else:
                    viewers["file-rdpgw"] = self.DesktopViewer(
                        domains[0]["id"],
                        protocol="file-rdpgw",
                        get_cookie=True,
                    )
            return viewers
        raise Error(
            "internal_server",
            "Jumperviewer token duplicated",
            traceback.format_exc(),
            description_code="generic_error",
        )

    def DesktopDirectViewer(self, desktop_id, viewer_txt, protocol):
        viewer_uri = viewer_txt["viewer"][0].split("/viewer/")[0] + "/vw/"

        jumpertoken = False
        with app.app_context():
            jumpertoken = (
                r.table("domains")
                .get(desktop_id)
                .pluck("jumperurl")
                .run(db.conn)["jumperurl"]
            )
        if not jumpertoken:
            jumpertoken = self.gen_jumpertoken(desktop_id)

        return {
            "kind": protocol,
            "viewer": viewer_uri + jumpertoken + "?protocol=" + protocol,
            "cookie": False,
        }

    def gen_jumpertoken(self, desktop_id, length=32):
        code = False
        while code == False:
            code = secrets.token_urlsafe(length)
            with app.app_context():
                found = list(
                    r.table("domains").get_all(code, index="jumperurl").run(db.conn)
                )
            if len(found) == 0:
                with app.app_context():
                    r.table("domains").get(desktop_id).update({"jumperurl": code}).run(
                        db.conn
                    )
                return code
        raise Error(
            "internal_server",
            "Unable to generate jumpertoken",
            traceback.format_exc(),
            description_code="generic_error",
        )

    def get_domain_hardware(self, domain_id):
        with app.app_context():
            hardware = (
                r.table("domains")
                .get(domain_id)
                .pluck({"create_dict": {"hardware", "reservables"}})
                .run(db.conn)["create_dict"]
            )
        if "isos" in hardware["hardware"]:
            with app.app_context():
                hardware["hardware"]["isos"] = list(
                    r.table("media")
                    .get_all(
                        r.args([i["id"] for i in hardware["hardware"]["isos"]]),
                        index="id",
                    )
                    .pluck("id", "name")
                    .run(db.conn)
                )
        if "floppies" in hardware["hardware"]:
            with app.app_context():
                hardware["hardware"]["floppies"] = list(
                    r.table("media")
                    .get_all(
                        r.args([i["id"] for i in hardware["hardware"]["floppies"]]),
                        index="id",
                    )
                    .pluck("id", "name")
                    .run(db.conn)
                )
        hardware["hardware"]["memory"] = hardware["hardware"]["memory"] / 1048576
        return hardware
