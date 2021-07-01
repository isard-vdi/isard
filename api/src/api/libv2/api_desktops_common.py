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

import secrets

class ApiDesktopsCommon:
    def __init__(self):
        None

    def DesktopViewer(self, desktop_id, protocol, get_cookie=False):
        if protocol in ['url','file']:
            direct_protocol = protocol
            protocol = 'vnc-html5'
        else:
            direct_protocol = False

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

        if not direct_protocol:
            return viewer_txt
        else:
            return self.DesktopDirectViewer(desktop_id, viewer_txt, direct_protocol)

    def DesktopViewerFromToken(self, token):
        with app.app_context():
            domains = list(r.table("domains").filter({"jumperurl": token}).run(db.conn))
        domains=[d for d in domains if d.get("tag_visible", True)]
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

    def DesktopDirectViewer(self, desktop_id, viewer_txt, protocol):
        log.error(viewer_txt)
        viewer_uri=viewer_txt['viewer'][0].split('/viewer/')[0]+'/vw/'

        jumpertoken=False
        with app.app_context():
            try:
                jumpertoken = r.table("domains").get(desktop_id).pluck('jumperurl').run(db.conn)['jumperurl']
            except:
                pass
        if jumpertoken == False:
            jumpertoken = self.gen_jumpertoken(desktop_id)
        
        return {'kind': protocol,'viewer':viewer_uri+jumpertoken+'?protocol='+protocol, 'cookie': False}

    def gen_jumpertoken(self, desktop_id, length=128):
        code = False
        while code == False:
            code = secrets.token_urlsafe(length) 
            found=list(r.table('domains').filter({'jumperurl':code}).run(db.conn))
            if len(found) == 0:
                with app.app_context():
                    r.table('domains').get(desktop_id).update({'jumperurl':code}).run(db.conn)                
                return code
        return False