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

from rethinkdb import RethinkDB; r = RethinkDB()
from rethinkdb.errors import ReqlTimeoutError

import logging
import traceback

from .flask_rethink import RDB
db = RDB(app)
db.init_app(app)

from ..auth.authentication import *

from ..libv2.isardViewer import isardViewer
isardviewer = isardViewer()

from .apiv2_exc import *

from .helpers import (
    _check,
    _parse_string,
    _parse_media_info,
    _disk_path,
    _random_password,
)

from .ds import DS 
ds = DS()

from ..libv2.isardViewer import isardViewer
isardviewer = isardViewer()

class ApiDeployments():
    def __init__(self):
        self.au=auth()

    def List(self,user_id):
        with app.app_context():
            deployments = list(r.table('deployments').get_all(user_id,index='user').pluck('id','name').merge(lambda deployment:
                        {
                            "totalDesktops": r.table('domains').get_all(deployment['id'],index='tag').count(),
                            "startedDesktops": r.table('domains').get_all(deployment['id'],index='tag').filter({'status':'Started'}).count()
                        }
                    ).run(db.conn))
        return deployments

    def Get(self,user_id,deployment_id):
        with app.app_context():
            if user_id != r.table('deployments').get(deployment_id).pluck('user').run(db.conn)['user']: raise
            desktops = list(r.table('domains').get_all(deployment_id,index='tag').pluck('id','user','name','description','status','create_dict').merge(lambda desktop:
                            {
                                "userName": r.table('users').get(desktop['user']).pluck('name')['name']
                            }
                        ).run(db.conn))
        for desktop in desktops:
            desktop['state']=desktop.pop('status')
            if desktop['state'] == 'Started':
                # We only return the direct browser url.
                # TODO: Check if it has RDP and send RDP instead of vnc?
                desktop['viewer'] = isardviewer.viewer_data(
                        desktop['id'], 'vnc-html5', get_cookie=False, get_dict=True
                    )
                desktop["viewers"] = []
                if "default" in desktop["create_dict"]["hardware"]["videos"]:
                    desktop["viewers"].extend(["spice", "browser"])
                if "wireguard" in desktop["create_dict"]["hardware"]["interfaces"]:
                    desktop["ip"] = d.get("viewer", {}).get("guest_ip")
                    if not desktop["ip"]:
                        desktop["state"] = "WaitingIP"
                    if desktop["os"].startswith("win"):
                        desktop["viewers"].extend(["rdp", "rdp-html5"])
            desktop.pop('create_dict')
        return desktops


        