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

from ..libv2.api_admin import ApiAdmin, admin_table_get, admin_table_update
from .decorators import is_admin_or_manager

admins = ApiAdmin()


@app.route("/api/v3/admin/domains", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_domains(payload):
    params = request.args
    if params.get("kind") == "desktop":
        domains = admins.ListDesktops(payload["user_id"])
    else:
        domains = admins.ListTemplates(payload["user_id"])
    if payload["role_id"] == "manager":
        domains = [d for d in domains if d["category"] == payload["category_id"]]
    return (
        json.dumps(domains),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/domains/xml/<id>", methods=["POST", "GET"])
@is_admin_or_manager
def api_v3_admin_domains_xml(payload, id):
    if request.method == "POST":
        data = request.get_json(force=True)
        data["status"] = "Updating"
        data["id"] = id
        admin_table_update("domains", data)
    return (
        json.dumps(admin_table_get("domains", pluck="xml", id=id)["xml"]),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/domains/server/<id>", methods=["POST", "GET"])
@is_admin_or_manager
def api_v3_admin_domains_server(payload, id):
    if request.method == "POST":
        admin_table_update("domains", id, request.get_json(force=True))
        return (
            json.dumps(admin_table_update),
            200,
            {"Content-Type": "application/json"},
        )
    server = admin_table_get(
        "domains",
        pluck="create_dict",
        id=id,
    )["create_dict"]
    return (
        json.dumps(server.get("server", False)),
        200,
        {"Content-Type": "application/json"},
    )
