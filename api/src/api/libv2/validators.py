#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
import os
import traceback

from .api_exceptions import Error
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)


def _validate_item(item, data, normalize=True):
    if not app.validators[item].validate(data):
        raise Error(
            "bad_request",
            "Data validation for "
            + item
            + " failed: "
            + str(app.validators[item].errors),
            traceback.format_stack(),
        )
    if normalize:
        return app.validators[item].normalized(data)
    return data


def _validate_table(table):
    if table not in app.system_tables:
        raise Error(
            "not_found",
            "Table " + table + " does not exist.",
            traceback.format_stack(),
        )


def _validate_alloweds(alloweds):
    None
