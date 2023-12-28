# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import traceback

from cachetools import TTLCache, cached
from flask import request
from isardvdi_common.api_exceptions import Error

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.api_admin import ApiAdmin, admin_table_get, admin_table_update
from ..libv2.api_desktop_events import templates_delete
from ..libv2.api_desktops_persistent import ApiDesktopsPersistent, domain_template_tree
from ..libv2.api_domains import ApiDomains
from ..libv2.api_storage import get_domains_delete_pending
from ..libv2.datatables import LogsDesktopsQuery
from .decorators import is_admin, is_admin_or_manager, ownsDomainId

admins = ApiAdmin()
desktops_persistent = ApiDesktopsPersistent()
domains = ApiDomains()


@app.route("/api/v3/admin/domains", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_domains(payload):
    params = request.get_json(force=True)
    domains = []
    if params.get("kind") == "desktop":
        categories = (
            json.loads(params.get("categories")) if params.get("categories") else None
        )
        if payload["role_id"] == "manager":
            categories = [payload["category_id"]]
        domains = admins.ListDesktops(
            categories,
        )
    else:
        domains = admins.ListTemplates(payload["user_id"])
        if payload["role_id"] == "manager":
            domains = [d for d in domains if d["category"] == payload["category_id"]]
    return (
        json.dumps(domains),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/domain/<domain_id>/details", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_details_data(payload, domain_id):
    ownsDomainId(payload, domain_id)
    return (
        json.dumps(admins.DesktopDetailsData(domain_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/domain/<domain_id>/viewer_data", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_deployment_viewer_data(payload, domain_id):
    ownsDomainId(payload, domain_id)
    return (
        json.dumps(admins.DesktopViewerData(domain_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/deployment/<deployment_id>/viewer_data", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_domain_viewer_data(payload, deployment_id):
    ownsDomainId(payload, deployment_id)
    return (
        json.dumps(admins.DeploymentViewerData(deployment_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/domains_status/<status>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_domains_status(payload, status):
    if status == "delete_pending":
        domains = (
            get_domains_delete_pending()
            if payload.get("role_id", "") == "admin"
            else get_domains_delete_pending(payload["category_id"])
        )
    elif payload.get("role_id", "") == "admin":
        domains = admins.domains_status_minimal(status)
    return (
        json.dumps(domains),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/domain/storage/<domain_id>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_desktop_storage(payload, domain_id):
    ownsDomainId(payload, domain_id)
    return (
        json.dumps(admins.get_domain_storage(domain_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/domains/xml/<domain_id>", methods=["POST", "GET"])
@is_admin
def api_v3_admin_domains_xml(payload, domain_id):
    if request.method == "POST":
        data = request.get_json(force=True)
        data["status"] = "Updating"
        data["id"] = domain_id
        admin_table_update("domains", data)
    return (
        json.dumps(admin_table_get("domains", domain_id, pluck="xml")["xml"]),
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


@app.route("/api/v3/admin/domain/template_tree/<desktop_id>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_desktop_template_tree(payload, desktop_id):
    ownsDomainId(payload, desktop_id)
    return (
        json.dumps(domain_template_tree(desktop_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/multiple_actions", methods=["POST"])
@is_admin_or_manager
def admin_multiple_actions_domains(payload):
    dict = request.get_json(force=True)
    selected_desktops = admins.CheckField("domains", "kind", "desktop", dict["ids"])
    for id in dict.get("ids"):
        ownsDomainId(payload, id)
    res = admins.MultipleActions(
        "domains", dict["action"], selected_desktops, payload["user_id"]
    )
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


@app.route("/api/v3/admin/templates/delete/<template_id>", methods=["DELETE"])
@is_admin_or_manager
def api_v3_admin_templates_delete(payload, template_id):
    templates_delete(template_id, payload["user_id"])
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@cached(TTLCache(maxsize=10, ttl=5))
@app.route("/api/v3/admin/domains/<field>/<kind>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_domains_field(payload, field, kind):
    return json.dumps(admins.get_domains_field(field, kind, payload))


# Render domain Hardware at domain details' Hardware table
@app.route("/api/v3/domain/hardware/<domain_id>", methods=["GET"])
@is_admin_or_manager
def api_v3_domain_hardware(payload, domain_id):
    ownsDomainId(payload, domain_id)
    return (
        json.dumps(domains.get_domain_details_hardware(domain_id)),
        200,
        {"Content-Type": "application/json"},
    )


@cached(TTLCache(maxsize=10, ttl=60))
@app.route("/api/v3/admin/logs_desktops", methods=["POST"])
@app.route("/api/v3/admin/logs_desktops/<view>", methods=["POST"])
@is_admin
def api_v3_logs_desktops(payload, view="raw"):
    if view == "raw":
        return (
            json.dumps(
                LogsDesktopsQuery(request.form).data,
                indent=4,
                sort_keys=True,
                default=str,
            ),
            200,
            {"Content-Type": "application/json"},
        )
    if view == "desktops_view":
        ld = LogsDesktopsQuery(request.form)
        ld.desktop_view
        return (
            json.dumps(
                ld.data,
                indent=4,
                sort_keys=True,
                default=str,
            ),
            200,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/desktops/<current_status>/<target_status>", methods=["PUT"])
@is_admin
def api_v3_desktops_status(payload, current_status, target_status):
    if not (target_status in ["Shutting-down", "Stopping", "StartingPaused", "Failed"]):
        raise Error("bad_request", "Invalid target status")
    desktops_persistent.change_status(current_status, target_status)

    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )
