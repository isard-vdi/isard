#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import time
from api import app
from datetime import datetime, timedelta
import pprint

from rethinkdb import RethinkDB

r = RethinkDB()
from rethinkdb.errors import ReqlTimeoutError

import logging as log

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..libv2.isardViewer import isardViewer

isardviewer = isardViewer()

from .apiv2_exc import *

from .ds import DS

ds = DS()

from .helpers import _check, _parse_string, _parse_media_info, _disk_path


class ApiDesktopsCommon:
    def __init__(self):
        None

    def DesktopViewer(self, desktop_id, protocol, get_cookie=False):
        try:
            viewer_txt = isardviewer.viewer_data(
                desktop_id, protocol, get_cookie=get_cookie
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
        return viewer_txt

    def DesktopViewerFromToken(self, token):
        with app.app_context():
            domains = list(r.table("domains").filter({"jumperurl": token}).run(db.conn))
        if len(domains) == 0:
            raise DesktopNotFound
        if len(domains) == 1:
            try:
                if domains[0]["status"] in ["Started", "Failed"]:
                    viewers = {
                        "vmName": domains[0]["name"],
                        "vmDescription": domains[0]["description"],
                        "spice-client": self.DesktopViewer(
                            domains[0]["id"], "spice-client", get_cookie=True
                        ),
                        "vnc-html5": self.DesktopViewer(
                            domains[0]["id"], "vnc-html5", get_cookie=True
                        ),
                    }
                    return viewers
                elif domains[0]["status"] == "Stopped":
                    ds.WaitStatus(domains[0]["id"], "Stopped", "Starting", "Started")
                    viewers = {
                        "vmName": domains[0]["name"],
                        "vmDescription": domains[0]["description"],
                        "spice-client": self.DesktopViewer(
                            domains[0]["id"], "spice-client", get_cookie=True
                        ),
                        "vnc-html5": self.DesktopViewer(
                            domains[0]["id"], "vnc-html5", get_cookie=True
                        ),
                    }
                    return viewers
            except:
                raise
        raise
