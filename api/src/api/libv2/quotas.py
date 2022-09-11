#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import logging as log

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from .quotas_process import QuotasProcess

qp = QuotasProcess()


class Quotas:
    def __init__(self):
        None

    def Get(self, user_id):
        return qp.get(user_id)

    def GetUserQuota(self, user_id):
        return qp.get_user(user_id)

    def GetCategoryQuota(self, category_id):
        return qp.get_category(category_id)

    def GetGroupQuota(self, group_id):
        return qp.get_group(group_id)

    def UserCreate(self, category_id, group_id):
        qp.check_new_autoregistered_user(category_id, group_id)

    def DesktopCreate(self, user_id):
        qp.check("NewDesktop", user_id)

    def DesktopStart(self, user_id):
        qp.check("NewConcurrent", user_id)

    def DesktopCreateAndStart(self, user_id):
        self.DesktopCreate(user_id)
        self.DesktopStart(user_id)

    def TemplateCreate(self, payload):
        qp.check("NewTemplate", payload["user_id"])

    def IsoCreate(self, user_id):
        return

    def deployment_create(self, user_id):
        qp.check("NewDesktop", user_id)

    def get_hardware_allowed(self, payload, domain_id=None):
        return qp.user_hardware_allowed(payload, kind=None, domain_id=domain_id)

    def get_hardware_kind_allowed(self, payload, kind):
        return qp.user_hardware_allowed(payload, kind, None)

    def limit_user_hardware_allowed(self, payload, create_dict):
        return qp.limit_user_hardware_allowed(payload, create_dict)

    # Timeouts
    def get_shutdown_timeouts(self, payload, desktop_id=None):
        return qp.get_shutdown_timeouts(payload, desktop_id=None)
