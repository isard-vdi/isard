# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import traceback

from flask import request

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.api_admin import (
    ApiAdmin,
    admin_domains_delete,
    admin_table_get,
    admin_table_update,
)
from ..libv2.api_desktops_persistent import ApiDesktopsPersistent
from ..libv2.api_exceptions import Error
from .decorators import is_admin_or_manager, ownsDomainId

admins = ApiAdmin()
desktops_persistent = ApiDesktopsPersistent()


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


@app.route("/api/v3/admin/desktops/tree_list/<id>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_desktops_tree_list(payload, id):
    user_id = payload["user_id"]
    return (
        json.dumps(admins.GetTemplateTreeList(id, user_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/multiple_actions", methods=["POST"])
@is_admin_or_manager
def admin_multiple_actions_domains(payload):
    dict = request.get_json(force=True)
    selected_desktops = admins.CheckField("domains", "kind", "desktop", dict["ids"])
    res = admins.MultipleActions("domains", dict["action"], selected_desktops)
    if res is True:
        json_data = json.dumps(
            {
                "title": "Processing",
                "text": "Actions will be processed",
                "type": "success",
            }
        )
        http_code = 200
    else:
        json_data = json.dumps(
            {
                "title": "Error",
                "text": res,
                "type": "error",
            }
        )
        http_code = 409
    return json_data, http_code, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/getAllTemplates", methods=["POST"])
@is_admin_or_manager
def getAllTemplates(payload):

    data = request.get_json()
    templates = admins.TemplatesByTerm(data["term"])

    if payload["role_id"] == "manager":
        templates = [d for d in templates if d["category"] == payload["category_id"]]

    return json.dumps(templates)


@app.route("/api/v3/admin/domains", methods=["DELETE"])
@is_admin_or_manager
def api_v3_admin_domains_delete(payload):
    if request.method == "DELETE":
        try:
            domains = request.get_json(force=True)
        except:
            import logging as log

            log.debug(traceback.format_exc())
            raise Error(
                "internal_server",
                "Internal server error ",
                traceback.format_stack(),
            )

        for i in domains:
            ownsDomainId(payload, i["id"])

        admin_domains_delete(domains)
        return json.dumps({}), 200, {"Content-Type": "application/json"}
