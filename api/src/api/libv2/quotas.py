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
# ~ from ..libv1.log import *
import logging as log

from rethinkdb.errors import ReqlTimeoutError

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from .quotas_process import QuotasProcess

qp = QuotasProcess()


class Quotas:
    def __init__(self):
        None

    def UserCreate(self, category_id, group_id):
        qp.check_new_autoregistered_user(category_id, group_id)

    def DesktopCreate(self, user_id):
        qp.check("NewDesktop", user_id)

    def DesktopStart(self, user_id):
        qp.check("NewConcurrent", user_id)

    def DesktopCreateAndStart(self, user_id):
        self.DesktopCreate(user_id)
        self.DesktopStart(user_id)

    def TemplateCreate(sefl, user_id):
        return

    def IsoCreate(sefl, user_id):
        return
