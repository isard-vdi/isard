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

import logging as log

from .flask_rethink import RDB
db = RDB(app)
db.init_app(app)

from ..auth.authentication import *

from ..libv2.isardViewer import isardViewer
isardviewer = isardViewer()

from .apiv2_exc import *

from .helpers import _check, _parse_string, _parse_media_info, _disk_path

from .ds import DS 
ds = DS()

from .helpers import _check, _random_password

class ApiSundry():
    def __init__(self):
        None

    def UpdateGuestAddr(self, domain_id, data):
        with app.app_context():
            if not _check(r.table('domains').get(domain_id).update(data).run(db.conn),'replaced'):
                raise UpdateFailed            
