# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json
import time

from flask import Response, render_template, request
from flask_login import current_user, login_required

from webapp import app

from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

from ...lib import trees

template_tree = trees.TemplateTree()


from .decorators import (
    isAdmin,
    isAdminManager,
    isAdminManagerAdvanced,
    isAdvanced,
    ownsidortag,
)


@app.route("/isard-admin/admin/domains/render/<nav>")
@login_required
@isAdminManager
def admin_domains(nav="Domains"):
    icon = ""
    if nav == "Desktops":
        icon = "desktop"
    if nav == "Templates":
        icon = "cube"
    if nav == "Bases":
        icon = "cubes"
    if nav == "Resources":
        icon = "arrows-alt"
        return render_template(
            "admin/pages/domains_resources.html", title=nav, nav=nav, icon=icon
        )
    if nav == "Bookables":
        icon = "briefcase"
        return render_template(
            "admin/pages/bookables.html", title=nav, nav=nav, icon=icon
        )
    if nav == "Priority":
        icon = "briefcase"
        return render_template(
            "admin/pages/bookables_priority.html", title=nav, nav=nav, icon=icon
        )
    else:
        return render_template(
            "admin/pages/domains.html", title=nav, nav=nav, icon=icon
        )


@app.route("/isard-admin/admin/mdomains", methods=["POST"])
@login_required
@isAdminManager
def admin_mdomains():
    dict = request.get_json(force=True)
    desktop_domains = app.adminapi.multiple_check_field(
        "domains", "kind", "desktop", dict["ids"]
    )
    res = app.adminapi.multiple_action("domains", dict["action"], desktop_domains)
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

    res = app.adminapi.multiple_action("domains", dict["action"], desktop_domains)
    return json.dumps({"test": 1}), 200, {"Content-Type": "application/json"}


@app.route("/isard-admin/advanced/mdomains", methods=["POST"])
@login_required
@isAdminManagerAdvanced
def admin_advanced_mdomains():
    dict = request.get_json(force=True)
    desktop_domains = app.adminapi.multiple_check_field(
        "domains", "kind", "desktop", dict["ids"]
    )
    if current_user.role == "advanced":
        tags = app.adminapi.user_owns_tag_ids(current_user.id, desktop_domains)
        if tags is not False:
            res = app.adminapi.multiple_action(
                "domains", dict["action"], desktop_domains
            )
            if res:
                if dict["action"] == "download_jumperurls":
                    return json.dumps(res), 200, {"Content-Type": "text/csv"}
                return (
                    json.dumps({"test": 1}),
                    200,
                    {"Content-Type": "application/json"},
                )
    return json.dumps({}), 500, {"Content-Type": "application/json"}


@app.route("/isard-admin/admin/domains/get/<kind>")
@app.route("/isard-admin/admin/domains/get")
@login_required
@isAdminManager
def admin_domains_get(kind=False):
    if kind:
        if kind == "Desktops":
            kind = "desktop"
        else:
            data = app.adminapi.get_admin_domains_with_derivates(kind="template")
            if current_user.role == "manager":
                data = [d for d in data if d["category"] == current_user.category]
            return json.dumps(data), 200, {"Content-Type": "application/json"}
    data = app.adminapi.get_admin_domains_with_derivates(kind=kind)
    if current_user.role == "manager":
        data = [d for d in data if d["category"] == current_user.category]
    return json.dumps(data), 200, {"Content-Type": "application/json"}


@app.route("/isard-admin/admin/domains/xml/<id>", methods=["POST", "GET"])
@login_required
@isAdmin
def admin_domains_xml(id):
    if request.method == "POST":
        data = request.get_json(force=True)
        data["status"] = "Updating"
        res = app.adminapi.update_table_dict("domains", id, data)
        if res:
            return json.dumps(res), 200, {"Content-Type": "application/json"}
        else:
            return json.dumps(res), 500, {"Content-Type": "application/json"}
    return (
        json.dumps(app.adminapi.get_admin_table("domains", pluck="xml", id=id)["xml"]),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/isard-admin/admin/domains/server/<id>", methods=["POST", "GET"])
@login_required
@isAdminManager
def admin_domains_server(id):
    if request.method == "POST":
        res = app.adminapi.update_table_dict(
            "domains", id, request.get_json(force=True)
        )
        if res:
            return json.dumps(res), 200, {"Content-Type": "application/json"}
        else:
            return json.dumps(res), 500, {"Content-Type": "application/json"}
    server = app.adminapi.get_admin_table(
        "domains", pluck="create_dict", id=id, flatten=False
    )["create_dict"]
    return (
        json.dumps(server.get("server", False)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/isard-admin/admin/domains/todelete/<id>", methods=["POST"])
@app.route("/isard-admin/admin/domains/todelete/<id>", methods=["GET"])
@login_required
@isAdminManager
def admin_domains_todelete(id=None):
    if request.method == "POST":
        res = app.adminapi.template_delete(id)
        if res:
            return json.dumps(res), 200, {"Content-Type": "application/json"}
        else:
            return json.dumps(res), 500, {"Content-Type": "application/json"}
    return (
        json.dumps(app.adminapi.template_delete_list(id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/isard-admin/admin/items/delete", methods=["POST"])
@login_required
@isAdminManager
def admin_items_delete():
    if request.method == "POST":
        try:
            args = request.get_json(force=True)
        except:
            args = request.form.to_dict()

        res = app.adminapi.items_delete(args)
        if res == False:
            return json.dumps(True), 200, {"Content-Type": "application/json"}
        else:
            return json.dumps(res), 500, {"Content-Type": "application/json"}


@app.route("/isard-admin/admin/domains/jumperurl/<id>")
@login_required
@ownsidortag
def admin_jumperurl(id):
    data = app.adminapi.get_jumperurl(id)
    return json.dumps(data), 200, {"Content-Type": "application/json"}


@app.route("/isard-admin/admin/domains/jumperurl_reset/<id>")
@login_required
@ownsidortag
def admin_jumperurl_reset(id):
    data = app.adminapi.jumperurl_reset(id)
    return json.dumps(data), 200, {"Content-Type": "application/json"}


@app.route("/isard-admin/admin/domains/jumperurl_disable/<id>")
@login_required
@ownsidortag
def admin_jumperurl_disable(id):
    data = app.adminapi.jumperurl_reset(id, disabled=True)
    return json.dumps(data), 200, {"Content-Type": "application/json"}


@app.route("/isard-admin/admin/domains/tree_list/<id>", methods=["GET"])
@login_required
@isAdminManager
def admin_domains_tree_list(id):
    return (
        json.dumps(template_tree.get_tree(id, current_user)),
        200,
        {"Content-Type": "application/json"},
    )


# ~ '''
# ~ VIRT BUILDER TESTS (IMPORT NEW BUILDERS?)
# ~ '''
# ~ @app.route('/isard-admin/admin/domains/virtrebuild')
# ~ @login_required
# ~ @isAdmin
# ~ def admin_domains_get_builders():
# ~ app.adminapi.update_virtbuilder()
# ~ app.adminapi.update_virtinstall()
# ~ return json.dumps(''), 200, {'Content-Type': 'application/json'}
