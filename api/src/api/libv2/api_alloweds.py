#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

from rethinkdb import RethinkDB

from api import app

from ..auth.authentication import *
from .api_exceptions import Error
from .flask_rethink import RDB

r = RethinkDB()


db = RDB(app)
db.init_app(app)


class ApiAlloweds:
    def get_table_term(self, table, field, value, pluck=False):
        with app.app_context():
            return list(
                r.table(table)
                .filter(lambda doc: doc[field].match("(?i)" + value))
                .pluck(pluck)
                .run(db.conn)
            )
