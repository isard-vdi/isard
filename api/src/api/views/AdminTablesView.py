# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json

from flask import request

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.api_admin import admin_table_list
from .decorators import is_admin_or_manager


@app.route("/api/v3/admin/table/<table>", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_table(payload, table):
    options = request.get_json(force=True)
    result = admin_table_list(
        table,
        options.get("order_by"),
        options.get("pluck"),
        options.get("without"),
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
    return (
        json.dumps(result),
        200,
        {"Content-Type": "application/json"},
    )
