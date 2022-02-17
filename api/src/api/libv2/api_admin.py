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
import logging
import traceback

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..auth.authentication import *
from .validators import _validate_table


def admin_table_list(table, order_by, pluck, without):
    _validate_table(table)

    if not pluck and not without:
        with app.app_context():
            return list(r.table(table).order_by(order_by).run(db.conn))

    if pluck and not without:
        with app.app_context():
            return list(r.table(table).pluck(pluck).order_by(order_by).run(db.conn))

    if not pluck and without:
        with app.app_context():
            return list(r.table(table).without(without).order_by(order_by).run(db.conn))

    if pluck and without:
        with app.app_context():
            return list(
                r.table(table)
                .pluck(pluck)
                .without(without)
                .order_by(order_by)
                .run(db.conn)
            )
