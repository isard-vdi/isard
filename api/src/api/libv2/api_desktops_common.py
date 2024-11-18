#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import time
import traceback

import pytz
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from .caches import get_document
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from datetime import datetime

from isardvdi_common.api_exceptions import Error

from ..libv2.api_logging import (
    logs_domain_event_directviewer,
    logs_domain_start_directviewer,
)
from ..libv2.api_scheduler import Scheduler
from ..libv2.bookings.api_booking import is_future
from ..libv2.helpers import _parse_desktop_booking, gen_payload_from_user
from .api_desktop_events import desktop_start
from .isardViewer import isardViewer, viewer_jwt

isardviewer = isardViewer()
scheduler = Scheduler()

import secrets


class ApiDesktopsCommon:
    def __init__(self):
        None

    def DesktopViewer(self, desktop_id, protocol, get_cookie=False, admin_role=False):
        if protocol in ["url", "file"]:
            direct_protocol = protocol
            protocol = "browser-vnc"
        else:
            direct_protocol = False

        viewer_txt = isardviewer.viewer_data(
            desktop_id, protocol=protocol, admin_role=admin_role
        )

        with app.app_context():
            r.table("domains").get(desktop_id).update(
                {"accessed": int(time.time())}
            ).run(db.conn)

        if not direct_protocol:
            return viewer_txt
        else:
            return self.DesktopDirectViewer(desktop_id, viewer_txt, direct_protocol)

    def DesktopViewerFromToken(self, token, start_desktop=True, request=None):
        domain = self.DesktopFromToken(token)

        booking = _parse_desktop_booking(domain)
        if booking.get("needs_booking"):
            if not booking.get("next_booking_start"):
                raise Error(
                    "precondition_required",
                    "Bookable desktop can't be started without a booking",
                    traceback.format_exc(),
                    "desktop_not_booked",
                )
            elif is_future(
                {
                    "start": datetime.strptime(
                        booking.get("next_booking_start"), "%Y-%m-%dT%H:%M%z"
                    ).astimezone(pytz.UTC)
                }
            ):
                raise Error(
                    "precondition_required",
                    "The next desktop booking is at "
                    + booking.get("next_booking_start"),
                    traceback.format_exc(),
                    "desktop_not_booked_until",
                    data=None,
                    params={"start": booking.get("next_booking_start")},
                )

        scheduled = False
        if start_desktop:
            if domain["status"] in ["Stopped", "Failed"]:
                desktop_start(domain["id"], wait_seconds=60)
                payload = gen_payload_from_user(domain["user"])
                scheduled = scheduler.add_desktop_timeouts(payload, domain["id"])
            else:
                logs_domain_event_directviewer(
                    domain["id"], "directviewer-access", user_request=request
                )
        viewers = {
            "desktopId": domain["id"],
            "jwt": viewer_jwt(domain["category"], domain["id"], minutes=30),
            "vmName": domain["name"],
            "vmDescription": domain["description"],
            "vmState": "Started",
            "scheduled": scheduled if scheduled else domain.get("scheduled"),
        }
        desktop_viewers = list(domain["guest_properties"]["viewers"].keys())
        if "file_spice" in desktop_viewers:
            viewers["file-spice"] = self.DesktopViewer(
                domain["id"], protocol="file-spice", get_cookie=True
            )
        if "browser_vnc" in desktop_viewers:
            viewers["browser-vnc"] = self.DesktopViewer(
                domain["id"], protocol="browser-vnc", get_cookie=True
            )
        if "browser_rdp" in desktop_viewers:
            if domain.get("viewer", True) == False:
                viewers["browser_rdp"] = {"kind": "browser", "protocol": "rdp"}
                viewers["vmState"] = "WaitingIP"
            elif not domain.get("viewer", {}).get("guest_ip"):
                viewers["browser_rdp"] = {"kind": "browser", "protocol": "rdp"}
                viewers["vmState"] = "WaitingIP"
            else:
                viewers["browser-rdp"] = self.DesktopViewer(
                    domain["id"],
                    protocol="browser-rdp",
                    get_cookie=True,
                )
        if "file_rdpgw" in desktop_viewers:
            if domain.get("viewer", True) == False:
                viewers["file-rdpgw"] = {"kind": "file", "protocol": "rdpgw"}
                viewers["vmState"] = "WaitingIP"
            elif not domain.get("viewer", {}).get("guest_ip"):
                viewers["file-rdpgw"] = {"kind": "file", "protocol": "rdpgw"}
                viewers["vmState"] = "WaitingIP"
            else:
                viewers["file-rdpgw"] = self.DesktopViewer(
                    domain["id"],
                    protocol="file-rdpgw",
                    get_cookie=True,
                )
        return viewers

    def DesktopFromToken(self, token):
        domains = []
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
                "Desktop not found or not visible",
                traceback.format_exc(),
                description_code="not_found",
            )
        if len(domains) == 1:
            return domains[0]
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
        hardware_db = get_document("domains", domain_id, ["create_dict"])
        hardware = {"hardware": hardware_db["hardware"]}
        if hardware_db.get("reservables"):
            hardware["reservables"] = hardware_db["reservables"]
        if "isos" in hardware["hardware"]:
            isos = hardware["hardware"]["isos"]
            hardware["hardware"]["isos"] = []
            # Loop instead of a get_all query to keep the isos array order
            for iso in isos:
                hardware["hardware"]["isos"].append(
                    get_document("media", iso["id"], ["id", "name"])
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

    def parse_desktop_queues(self, data):
        users = {}
        categories = {}

        domains = list(
            r.table("domains")
            .get_all(r.args([d["desktop_id"] for d in data]), index="id")
            .pluck("id", "user", "category")
            .run(db.conn)
        )

        for i in range(len(data)):
            desktop_id = data[i]["desktop_id"]

            user_id = domains[i]["user"]
            category_id = domains[i]["category"]

            # add user_id to users
            users[user_id] = users.get(user_id, {})
            # add data to users[user_id]
            users[user_id][desktop_id] = data[i]

            # add category_id to categories
            categories[category_id] = categories.get(category_id, {})
            # add data to categories[category_id]
            categories[category_id][desktop_id] = data[i]

        return users, categories
