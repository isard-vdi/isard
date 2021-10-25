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


from .quotas_exc import *
from .webapp_quotas import WebappQuotas

wq = WebappQuotas()


class Quotas:
    def __init__(self):
        None

    def UserCreate(self, category_id, group_id):
        exces = wq.check_new_autoregistered_user(category_id, group_id)
        if exces != False:
            if "category" in exces:
                raise QuotaCategoryNewUserExceeded
            if "group" in exces:
                raise QuotaGroupNewUserExceeded

        return False

    def DesktopCreate(self, user_id):
        exces = wq.check("NewDesktop", user_id)
        if exces != False:
            if "category" in exces:
                raise QuotaCategoryNewDesktopExceeded
            if "group" in exces:
                raise QuotaGroupNewDesktopExceeded
            raise QuotaUserNewDesktopExceeded

        return False

    def DesktopStart(self, user_id):
        exces = wq.check("NewConcurrent", user_id)
        if exces != False:
            if "CPU" in exces:
                if "category" in exces:
                    raise QuotaCategoryVcpuExceeded
                if "group" in exces:
                    raise QuotaGroupVcpuExceeded
                raise QuotaUserVcpuExceeded
            if "MEMORY" in exces:
                if "category" in exces:
                    raise QuotaCategoryMemoryExceeded
                if "group" in exces:
                    raise QuotaGroupMemoryExceeded
                raise QuotaUserMemoryExceeded

            if "category" in exces:
                raise QuotaCategoryConcurrentExceeded
            if "group" in exces:
                raise QuotaGroupNewConcurrentExceeded
            raise QuotaUserConcurrentExceeded

        return False

    def DesktopCreateAndStart(self, user_id):
        self.DesktopCreate(user_id)
        self.DesktopStart(user_id)

    def TemplateCreate(sefl, user_id):
        return False

    def IsoCreate(sefl, user_id):
        return False
