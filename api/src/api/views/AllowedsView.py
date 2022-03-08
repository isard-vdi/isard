# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json

from flask import request

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.api_alloweds import ApiAlloweds
from ..libv2.api_exceptions import Error
from .decorators import has_token

alloweds = ApiAlloweds()


# Gets all list of roles, categories, groups and users from a 2+ chars term
@app.route("/api/v3/admin/alloweds/term/<table>", methods=["POST"])
@has_token
def alloweds_table_term(payload, table):
    if table not in ["roles", "categories", "groups", "users"]:
        raise Error("not_found", "The given table doesn't exist")
    data = request.get_json(force=True)
    data["pluck"] = ["id", "name"]
    if payload["role_id"] == "admin":
        if table == "groups":
            result = alloweds.get_table_term(
                table, "id", data["term"], pluck=["id", "name", "parent_category"]
            )
        elif table == "users":
            result = alloweds.get_table_term(
                table, "id", data["term"], pluck=["id", "name", "uid"]
            )
        else:
            result = alloweds.get_table_term(
                table, "name", data["term"], pluck=data["pluck"]
            )
    else:
        if table == "roles":
            result = alloweds.get_table_term(
                table, "name", data["term"], pluck=data["pluck"]
            )
        if table == "categories":
            result = alloweds.get_table_term(
                table, "name", data["term"], pluck=data["pluck"]
            )
            result = [c for c in result if c["id"] == payload["category_id"]]
        if table == "groups":
            result = alloweds.get_table_term(
                table, "id", data["term"], pluck=["id", "name", "parent_category"]
            )
            result = [
                g for g in result if g["parent_category"] == payload["category_id"]
            ]
        if table == "users":
            result = alloweds.get_table_term(
                table, "name", data["term"], pluck=["id", "name", "category", "uid"]
            )
            result = [u for u in result if u["category"] == payload["category_id"]]
    return json.dumps(result), 200, {"Content-Type": "application/json"}
