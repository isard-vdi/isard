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

from rethinkdb.errors import ReqlNonExistenceError, ReqlTimeoutError

from .api_exceptions import ValidateError
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from .helpers import (  # _disk_path,; _parse_desktop,; _parse_media_info,; _parse_string,; _random_password,
    _check,
)


def _sys_tables():
    with app.app_context():
        return r.table_list().run(db.conn)


system_tables = _sys_tables()


def _validate_table(table):
    if table not in system_tables:
        raise ValidateError(
            "not_found",
            "Table " + table + " does not exist.",
            traceback.format_stack(),
        )


def _validate_alloweds(alloweds):
    None
