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

from ..libv2.isardViewer import isardViewer

isardviewer = isardViewer()

from .apiv2_exc import *
from .ds import DS

ds = DS()

import secrets

from .api_exceptions import Error
from .helpers import _check, _disk_path, _parse_media_info, _parse_string


class ApiDesktopsCommon:
    def __init__(self):
        None

    def DesktopViewer(self, desktop_id, protocol, get_cookie=False):
        if protocol in ["url", "file"]:
            direct_protocol = protocol
            protocol = "browser-vnc"
        else:
            direct_protocol = False

        try:
            viewer_txt = isardviewer.viewer_data(
                desktop_id, protocol=protocol, get_cookie=get_cookie
            )
        except DesktopNotFound:
            raise
        except DesktopNotStarted:
            raise
        except NotAllowed:
            raise
        except ViewerProtocolNotFound:
            raise
        except ViewerProtocolNotImplemented:
            raise

        if not direct_protocol:
            return viewer_txt
        else:
            return self.DesktopDirectViewer(desktop_id, viewer_txt, direct_protocol)

    def DesktopViewerFromToken(self, token):
        with app.app_context():
            all_domains = list(
                r.table("domains").filter({"jumperurl": token}).run(db.conn)
            )
        domains = [d for d in all_domains if d.get("tag_visible", True)]
        if len(domains) == 0:
            if len(all_domains):
                raise Error("forbidden", "Deployment owner has the deployment hidden")
            else:
                raise Error("not_found", "Jumperurl token not found")
        if len(domains) == 1:
            try:
                if domains[0]["status"] in ["Started", "Failed"]:
                    viewers = {
                        "vmName": domains[0]["name"],
                        "vmDescription": domains[0]["description"],
                        "file-spice": self.DesktopViewer(
                            domains[0]["id"], "file-spice", get_cookie=True
                        ),
                        "browser-vnc": self.DesktopViewer(
                            domains[0]["id"], "browser-vnc", get_cookie=True
                        ),
                    }
                    return viewers
                elif domains[0]["status"] == "Stopped":
                    ds.WaitStatus(domains[0]["id"], "Stopped", "Starting", "Started")
                    viewers = {
                        "vmName": domains[0]["name"],
                        "vmDescription": domains[0]["description"],
                        "file-spice": self.DesktopViewer(
                            domains[0]["id"], "file-spice", get_cookie=True
                        ),
                        "browser-vnc": self.DesktopViewer(
                            domains[0]["id"], "browser-vnc", get_cookie=True
                        ),
                    }
                    return viewers
            except:
                raise Error(
                    "internal_server",
                    "Unable to start domain at jumperurl",
                    traceback.format_exc(),
                )
        raise Error("conflict", "Two domains share the same jumperurl token!")

    def DesktopDirectViewer(self, desktop_id, viewer_txt, protocol):
        log.error(viewer_txt)
        viewer_uri = viewer_txt["viewer"][0].split("/viewer/")[0] + "/vw/"

        jumpertoken = False
        with app.app_context():
            try:
                jumpertoken = (
                    r.table("domains")
                    .get(desktop_id)
                    .pluck("jumperurl")
                    .run(db.conn)["jumperurl"]
                )
            except:
                pass
        if jumpertoken == False:
            jumpertoken = self.gen_jumpertoken(desktop_id)

        return {
            "kind": protocol,
            "viewer": viewer_uri + jumpertoken + "?protocol=" + protocol,
            "cookie": False,
        }

    def gen_jumpertoken(self, desktop_id, length=128):
        code = False
        while code == False:
            code = secrets.token_urlsafe(length)
            with app.app_context():
                found = list(
                    r.table("domains").filter({"jumperurl": code}).run(db.conn)
                )
            if len(found) == 0:
                with app.app_context():
                    r.table("domains").get(desktop_id).update({"jumperurl": code}).run(
                        db.conn
                    )
                return code
        return False
