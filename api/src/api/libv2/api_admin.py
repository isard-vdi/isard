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
import logging as log
import traceback

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from ..auth.authentication import *
from .api_exceptions import Error
from .helpers import _check, _parse_string
from .validators import _validate_item, _validate_table


def admin_table_list(table, order_by, pluck, without, id=None):
    _validate_table(table)

    if not pluck and not without:
        with app.app_context():
            if not id:
                return list(r.table(table).order_by(order_by).run(db.conn))
            else:
                return r.table(table).get(id).run(db.conn)

    if pluck and not without:
        with app.app_context():
            if not id:
                return list(r.table(table).pluck(pluck).order_by(order_by).run(db.conn))
            else:
                r.table(table).get(id).pluck(pluck).run(db.conn)

    if not pluck and without:
        with app.app_context():
            if not id:
                return list(
                    r.table(table).without(without).order_by(order_by).run(db.conn)
                )
            else:
                return r.table(table).get(id).without(without).run(db.conn)

    if pluck and without:
        with app.app_context():
            if not id:
                return list(
                    r.table(table)
                    .pluck(pluck)
                    .without(without)
                    .order_by(order_by)
                    .run(db.conn)
                )
            else:
                return r.table(table).get(id).pluck(pluck).without(without).run(db.conn)


def admin_table_insert(table, data):
    if data["id"] == None:
        data["id"] = _parse_string(data["name"])
    _validate_table(table)
    if table == "interfaces":
        _validate_item(table, data)
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
    if table == "interfaces":
        _validate_item(table, data)
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


def admin_table_get(table, pluck=False, id=False):
    _validate_table(table)
    with app.app_context():
        if pluck and id:
            data = r.table(table).get(id).pluck(pluck).run(db.conn)
            return data


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

    def GetTemplateTreeList(self, template_id, user_id):
        levels = {}
        derivated = self.TemplateTreeList(template_id, user_id)
        for n in derivated:
            levels.setdefault(n["parent"], []).append(n)
        recursion = self.TemplateTreeRecursion(template_id, levels)
        with app.app_context():
            user_id = r.table("users").get(user_id).run(db.conn)
            d = (
                r.db("isard")
                .table("domains")
                .get(template_id)
                .pluck(
                    "id",
                    "name",
                    "kind",
                    "category",
                    "group",
                    "user",
                    "username",
                    "status",
                    "parents",
                )
                .run(db.conn)
            )
        root = [
            {
                "id": d["id"],
                "title": d["name"],
                "expanded": True,
                "unselectable": False
                if user_id["role"] == "manager" or user_id["role"] == "admin"
                else True,
                "selected": True if user_id["id"] == d["user"] else False,
                "parent": d["parents"][-1]
                if "parents" in d.keys() and len(d["parents"]) > 0
                else "",
                "user": d["username"],
                "category": d["category"],
                "group": d["group"].split(d["category"] + "-")[1],
                "kind": d["kind"] if d["kind"] == "desktop" else "template",
                "status": d["status"],
                "icon": "fa fa-desktop" if d["kind"] == "desktop" else "fa fa-cube",
                "children": recursion,
            }
        ]
        return root

    def TemplateTreeRecursion(self, template_id, levels):
        nodes = [dict(n) for n in levels.get(template_id, [])]
        for n in nodes:
            children = self.TemplateTreeRecursion(n["id"], levels)
            if children:
                n["children"] = children
            for c in children:
                if c["unselectable"] == True:
                    n["unselectable"] = True
                    break
        return nodes

    def TemplateTreeList(self, template_id, user_id):
        with app.app_context():
            user_id = r.table("users").get(user_id).run(db.conn)
            template = (
                r.db("isard")
                .table("domains")
                .get(template_id)
                .pluck(
                    "id",
                    "name",
                    "kind",
                    "category",
                    "group",
                    "user",
                    "username",
                    "status",
                    "parents",
                )
                .run(db.conn)
            )
            derivated = list(
                r.db("isard")
                .table("domains")
                .pluck(
                    "id",
                    "name",
                    "kind",
                    "category",
                    "group",
                    "user",
                    "username",
                    "status",
                    "parents",
                )
                .filter(lambda derivates: derivates["parents"].contains(template_id))
                .run(db.conn)
            )
        if user_id["role"] == "manager":
            if template["category"] != user_id["category"]:
                return []
            derivated = [d for d in derivated if d["category"] == user_id["category"]]
        fancyd = []
        for d in derivated:
            if user_id["role"] == "manager" or user_id["role"] == "admin":
                fancyd.append(
                    {
                        "id": d["id"],
                        "title": d["name"],
                        "expanded": True,
                        "unselectable": False,
                        "selected": True if user_id["id"] == d["user"] else False,
                        "parent": d["parents"][-1],
                        "user": d["username"],
                        "category": d["category"],
                        "group": d["group"].split(d["category"] + "-")[1],
                        "kind": d["kind"] if d["kind"] == "desktop" else "template",
                        "status": d["status"],
                        "icon": "fa fa-desktop"
                        if d["kind"] == "desktop"
                        else "fa fa-cube",
                    }
                )
            else:
                ## It can only be an advanced user
                fancyd.append(
                    {
                        "id": d["id"],
                        "title": d["name"],
                        "expanded": True,
                        "unselectable": False if user_id["id"] == d["user"] else True,
                        "selected": True if user_id["id"] == d["user"] else False,
                        "parent": d["parents"][-1],
                        "user": d["username"],
                        "category": d["category"],
                        "group": d["group"].split(d["category"] + "-")[1],
                        "kind": d["kind"] if d["kind"] == "desktop" else "template",
                        "status": d["status"],
                        "icon": "fa fa-desktop"
                        if d["kind"] == "desktop"
                        else "fa fa-cube",
                    }
                )
        return fancyd
