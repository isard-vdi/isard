#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3
import ipaddress
import os
import time
import traceback
from datetime import datetime, timedelta
from pprint import pprint

import requests
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from rethinkdb.errors import ReqlNonExistenceError, ReqlTimeoutError

from .apiv2_exc import *
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..auth.authentication import *
from .apiv2_exc import *
from .ds import DS
from .helpers import _check, _disk_path, _parse_media_info, _parse_string

# from ..libv2.isardViewer import isardViewer
# isardviewer = isardViewer()


# from ..libv2.isardVpn import isardVpn
# isardVpn = isardVpn()


ds = DS()

import socket
from subprocess import check_call, check_output

from .helpers import _check, _random_password


class ApiMedia:
    def __init__(self):
        None

    def Get(self, payload):
        try:
            with app.app_context():
                medias = list(r.table("media").run(db.conn))
            alloweds = []
            for media in medias:
                # with app.app_context():
                #     media['username']=r.table('users').get(media['user']).pluck('name').run(db.conn)['name']
                if payload["role_id"] == "admin":
                    alloweds.append(media)
                    continue
                if (
                    payload["role_id"] == "manager"
                    and payload["category_id"] == media["category"]
                ):
                    alloweds.append(media)
                    continue
                if not payload.get("user_id", False):
                    continue
                if media["user"] == payload["user_id"]:
                    alloweds.append(media)
                    continue
                if media["allowed"]["roles"] is not False:
                    if len(media["allowed"]["roles"]) == 0:
                        alloweds.append(media)
                        continue
                    else:
                        if payload["role_id"] in media["allowed"]["roles"]:
                            alloweds.append(media)
                            continue
                if media["allowed"]["categories"] is not False:
                    if len(media["allowed"]["categories"]) == 0:
                        alloweds.append(media)
                        continue
                    else:
                        if payload["category_id"] in media["allowed"]["categories"]:
                            alloweds.append(media)
                            continue
                if media["allowed"]["groups"] is not False:
                    if len(media["allowed"]["groups"]) == 0:
                        alloweds.append(media)
                        continue
                    else:
                        if payload["group_id"] in media["allowed"]["groups"]:
                            alloweds.append(media)
                            continue
                if media["allowed"]["users"] is not False:
                    if len(media["allowed"]["users"]) == 0:
                        alloweds.append(media)
                        continue
                    else:
                        if payload["user_id"] in media["allowed"]["users"]:
                            alloweds.append(media)
                            continue
            return alloweds
        except Exception as e:
            raise UserMediaError
