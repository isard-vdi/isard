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

from ..auth.authentication import *
from ..libv2.isardViewer import isardViewer

isardviewer = isardViewer()

from .apiv2_exc import *
from .ds import DS
from .helpers import _check, _disk_path, _parse_media_info, _parse_string

ds = DS()

from .helpers import _check, _random_password


class ApiSundry:
    def __init__(self):
        None

    def UpdateGuestAddr(self, domain_id, data):
        with app.app_context():
            if not _check(
                r.table("domains").get(domain_id).update(data).run(db.conn), "replaced"
            ):
                raise UpdateFailed
