# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json

from flask import Response, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from webapp import app

from ..lib.log import *
from .decorators import maintenance, ownsid, ownsidortag


@app.route("/isard-admin/media", methods=["GET"])
@login_required
@maintenance
def media():
    return render_template("pages/media.html", nav="Media")


@app.route("/isard-admin/media/get/")
@login_required
@maintenance
def media_get():
    data = app.isardapi.get_user_media(current_user.id)
    return json.dumps(data), 200, {"Content-Type": "application/json"}


@app.route("/isard-admin/media/get/shared")
@login_required
@maintenance
def media_get_shared():
    data = app.isardapi.get_all_alloweds_table(
        "media", current_user.id, pluck=False, skipOwner=True
    )
    data = [d for d in data if d["status"] in ["Stopped", "Downloaded"]]

    return json.dumps(data), 200, {"Content-Type": "application/json"}


@app.route("/isard-admin/domain/media", methods=["POST"])
@login_required
@maintenance
def domain_media():
    if request.method == "POST":
        data = request.get_json(force=True)
        return (
            json.dumps(app.isardapi.get_domain_media(data["pk"])),
            200,
            {"Content-Type": "application/json"},
        )
    return url_for("media")


@app.route("/isard-admin/domain/media_list", methods=["POST"])
@login_required
@maintenance
def domain_media_list():
    if request.method == "POST":
        data = request.get_json(force=True)
        return (
            json.dumps(app.isardapi.get_domain_media_list(data["pk"])),
            200,
            {"Content-Type": "application/json"},
        )
    return url_for("media")


@app.route("/isard-admin/media/installs")
@login_required
@maintenance
def media_installs_get():
    return (
        json.dumps(app.isardapi.get_media_installs()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/isard-admin/media/select2/post", methods=["POST"])
@login_required
@maintenance
def media_select2_post():
    if request.method == "POST":
        data = request.get_json(force=True)
        if "pluck" not in data.keys():
            data["pluck"] = False
        if data["kind"] == "isos":
            kind = "iso"
        if data["kind"] == "floppies":
            kind = "floppy"
        # ~ if 'order' not in data.keys():
        # ~ data['order']=False
        result = app.isardapi.get_all_table_allowed_term(
            "media",
            kind,
            "name",
            data["term"],
            current_user.id,
            pluck=["id", "name", "status", "category"],
        )
        result = [r for r in result if r["status"] in ["Stopped", "Downloaded"]]
        if current_user.role != "admin":
            result = [
                r
                for r in result
                if r["category"] == current_user.category or r["category"] == "default"
            ]
        # ~ result=app.adminapi.get_admin_table_term('media','name',data['term'],kind=kind,pluck=data['pluck'])
        return json.dumps(result), 200, {"Content-Type": "application/json"}
    return json.dumps("Could not select."), 500, {"Content-Type": "application/json"}


# ~ @app.route('/isard-admin/admin/table/<table>/post', methods=["POST"])
# ~ @login_required
# ~ @isAdmin
# ~ def admin_table_post(table):
# ~ if request.method == 'POST':
# ~ data=request.get_json(force=True)
# ~ if 'pluck' not in data.keys():
# ~ data['pluck']=False
# ~ #~ if 'order' not in data.keys():
# ~ #~ data['order']=False
# ~ result=app.adminapi.get_admin_table_term(table,'name',data['term'],pluck=data['pluck'])
# ~ return json.dumps(result), 200, {'Content-Type':'application/json'}
# ~ return json.dumps('Could not delete.'), 500, {'Content-Type':'application/json'}
