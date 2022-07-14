# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json
import time

from flask import render_template, request
from flask_login import current_user, login_required

from webapp import app

from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

from ...lib import trees

template_tree = trees.TemplateTree()

from .decorators import isAdmin, isAdminManager, isAdminManagerAdvanced


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
