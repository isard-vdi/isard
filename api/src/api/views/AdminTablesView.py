# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log

from flask import request

#!flask/bin/python
# coding=utf-8
from api import app

from .._common.api_exceptions import Error
from ..libv2.api_admin import (
    admin_table_delete,
    admin_table_get,
    admin_table_insert,
    admin_table_list,
    admin_table_update,
)
from .decorators import is_admin, is_admin_or_manager


@app.route("/api/v3/admin/table/<table>", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_table(payload, table):
    options = request.get_json(force=True)
    if options.get("id") and not options.get("index"):
        result = admin_table_get(table, options.get("id"), pluck=options.get("pluck"))
    else:
        result = admin_table_list(
            table,
            options.get("order_by"),
            options.get("pluck"),
            options.get("without"),
            options.get("id"),
            options.get("index"),
        )

    if payload["role_id"] == "manager":
        if table == "categories":
            result = [
                {**r, **{"editable": False}}
                for r in result
                if r["id"] == payload["category_id"]
            ]
        if table == "groups":
            result = [
                r
                for r in result
                if "parent_category" in r.keys()
                and r["parent_category"] == payload["category_id"]
            ]
        if table == "roles":
            result = [r for r in result if r["id"] != "admin"]
        if table == "media":
            result = [r for r in result if r["category"] == payload["category_id"]]
        if table == "secrets":
            raise Error("forbidden", "Not enough rights.")

    return (
        json.dumps(result),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/table/add/<table>", methods=["POST"])
@is_admin
def api_v3_admin_insert_table(payload, table):
    data = request.get_json()
    admin_table_insert(table, data)
    return (json.dumps({}), 200, {"Content-Type": "application/json"})


@app.route("/api/v3/admin/table/update/<table>", methods=["PUT"])
@is_admin
def api_v3_admin_update_table(payload, table):
    data = request.get_json()
    admin_table_update(table, data)
    return (json.dumps({}), 200, {"Content-Type": "application/json"})


@app.route("/api/v3/admin/table/<table>/<item_id>", methods=["DELETE"])
@is_admin
def api_v3_admin_delete_table(payload, table, item_id):
    admin_table_delete(table, item_id)
    return (json.dumps({}), 200, {"Content-Type": "application/json"})
