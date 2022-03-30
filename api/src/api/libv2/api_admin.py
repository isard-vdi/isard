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

from .api_exceptions import Error

r = RethinkDB()
import logging
import traceback

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..auth.authentication import *
from .api_exceptions import Error
from .helpers import _check, _parse_string
from .validators import _validate_item, _validate_table


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


def admin_table_insert(table, data):
    data["id"] = _parse_string(data["name"])
    _validate_table(table)
    with app.app_context():
        if r.table(table).get(data["id"]).run(db.conn) == None:
            if not _check(r.table(table).insert(data).run(db.conn), "inserted"):
                raise Error(
                    "internal_server",
                    "Internal server error ",
                    traceback.format_exc(),
                )
        else:
            raise Error(
                "conflict", "Id " + data["id"] + " already exists in table " + table
            )


def admin_table_update(table, data):
    _validate_table(table)
    with app.app_context():
        if r.table(table).get(data["id"]).run(db.conn):
            if not _check(
                r.table(table).get(data["id"]).update(data).run(db.conn),
                "replaced",
            ):
                raise Error(
                    "internal_server",
                    "Internal server error",
                    traceback.format_exc(),
                )


def admin_table_delete(table, data):
    _validate_table(table)
    with app.app_context():
        if r.table(table).get(data["id"]).run(db.conn):
            if not _check(
                r.table(table).get(data["id"]).delete().run(db.conn),
                "deleted",
            ):
                raise Error(
                    "internal_server",
                    "Internal server error",
                    traceback.format_exc(),
                )


class ApiAdmin:
    def ListDesktops(self, user_id):
        with app.app_context():
            if r.table("users").get(user_id).run(db.conn) == None:
                raise Error(
                    "not_found", "Not found user_id " + user_id, traceback.format_exc()
                )
        try:
            with app.app_context():
                domains = list(
                    r.table("domains")
                    .get_all("desktop", index="kind")
                    .order_by("name")
                    .pluck(
                        "id",
                        "icon",
                        "image",
                        "server",
                        "hyp_started",
                        "name",
                        "kind",
                        "description",
                        "status",
                        "username",
                        "category",
                        "group",
                        "accessed",
                        "detail",
                        {
                            "create_dict": {
                                "hardware": {
                                    "video": True,
                                    "vcpus": True,
                                    "memory": True,
                                    "interfaces": True,
                                    "graphics": True,
                                    "videos": True,
                                    "boot_order": True,
                                    "forced_hyp": True,
                                },
                                "origin": True,
                            }
                        },
                    )
                    .run(db.conn)
                )
            return domains
        except Exception:
            raise Error(
                "internal_server",
                "Internal server error " + user_id,
                traceback.format_exc(),
            )

    def ListTemplates(self, user_id):
        with app.app_context():
            if r.table("users").get(user_id).run(db.conn) == None:
                raise Error(
                    "not_found", "Not found user_id " + user_id, traceback.format_exc()
                )

        try:
            with app.app_context():
                domains = list(
                    r.table("domains")
                    .get_all("template", index="kind")
                    .pluck(
                        "id",
                        "icon",
                        "image",
                        "server",
                        "hyp_started",
                        "name",
                        "kind",
                        "description",
                        "username",
                        "category",
                        "group",
                        "enabled",
                        "derivates",
                        "accessed",
                        "detail",
                        {
                            "create_dict": {
                                "hardware": {
                                    "video": True,
                                    "vcpus": True,
                                    "memory": True,
                                    "interfaces": True,
                                    "graphics": True,
                                    "videos": True,
                                    "boot_order": True,
                                    "forced_hyp": True,
                                },
                                "origin": True,
                            }
                        },
                    )
                    .merge(
                        lambda domain: {
                            "derivates": r.db("isard")
                            .table("domains")
                            .get_all([1, domain["id"]], index="parents")
                            .distinct()
                            .count()
                        }
                    )
                    .order_by("name")
                    .run(db.conn)
                )
            return domains
        except Exception:
            raise Error(
                "internal_server",
                "Internal server error " + user_id,
                traceback.format_exc(),
            )
