#!/usr/bin/env python
# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
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
            traceback.format_exc(),
        )
    if normalize:
        return app.validators[item].normalized(data)
    return data


def _validate_table(table):
    if table not in app.system_tables:
        raise Error(
            "not_found",
            "Table " + table + " does not exist.",
            traceback.format_exc(),
        )


def _validate_alloweds(alloweds):
    None


def check_user_duplicated_domain_name(item_id, name, user_id, kind="desktop"):
    if (
        r.table("domains")
        .get_all([kind, user_id], index="kind_user")
        .filter(lambda item: (item["name"] == name.strip()) & (item["id"] != item_id))
        .count()
        .run(db.conn)
        > 0
    ):
        raise Error(
            "conflict",
            "User " + user_id + " already has " + str(kind) + " with name " + name,
            str(kind).capitalize() + " with name " + name + " already exists",
            traceback.format_exc(),
        )
