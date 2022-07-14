# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import rethinkdb as r

#!/usr/bin/env python
# coding=utf-8
from flask import Response, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from webapp import app

from ..lib.flask_rethink import RethinkDB
from ..lib.log import *
from .decorators import isAdvanced, maintenance, ownsid

db = RethinkDB(app)
db.init_app(app)

import json
import time


@app.route("/isard-admin/desktops")
@login_required
@maintenance
def desktops():
    return render_template("pages/desktops.html", title="Desktops", nav="Desktops")


@app.route("/isard-admin/desktops/get")
@login_required
@maintenance
def desktops_get():
    return (
        json.dumps(app.isardapi.get_user_domains(current_user.id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/isard-admin/desktops/download_viewer/<os>/<id>")
@login_required
@maintenance
@ownsid
def viewer_download(os, id):
    try:
        extension, mimetype, consola = app.isardapi.get_viewer_ticket(id, os)
        return Response(
            consola,
            mimetype=mimetype,
            headers={"Content-Disposition": "attachment;filename=consola." + extension},
        )
    except Exception as e:
        log.error("Download viewer error:" + str(e))
        return Response("Error in viewer", mimetype="application/txt")


# ~ #~ Serves desktops and templates (domains)
@app.route("/isard-admin/domains/update", methods=["POST"])
@login_required
@maintenance
@ownsid
def domains_update():
    if request.method == "POST":
        try:
            args = request.get_json(force=True)
        except:
            args = request.form.to_dict()
        try:
            exceeded = app.isardapi.check_quota_limits("NewConcurrent", current_user.id)
            if exceeded != False:
                return (
                    json.dumps("Quota for starting domains full. " + exceeded),
                    500,
                    {"Content-Type": "application/json"},
                )
            if app.isardapi.update_table_value(
                "domains", args["pk"], args["name"], args["value"]
            ):
                return json.dumps("Updated"), 200, {"Content-Type": "application/json"}
            else:
                return (
                    json.dumps("This is not a valid value."),
                    500,
                    {"Content-Type": "application/json"},
                )
        except Exception as e:
            return (
                json.dumps("Wrong parameters."),
                500,
                {"Content-Type": "application/json"},
            )


# Gets all allowed for a domain
@app.route("/isard-admin/domain/alloweds/select2", methods=["POST"])
@login_required
@maintenance
def domain_alloweds_select2():
    allowed = request.get_json(force=True)["allowed"]
    return json.dumps(app.isardapi.get_alloweds_select2(allowed))


# Get all templates allowed for current_user
@app.route("/isard-admin/desktops/getAllTemplates", methods=["GET"])
@login_required
@maintenance
def getAllTemplates():
    templates = app.isardapi.get_all_alloweds_domains(current_user.id)
    templates = [t for t in templates if t["status"] == "Stopped"]
    if current_user.role != "admin":
        templates = [
            t
            for t in templates
            if t["category"] == current_user.category
            or t["role"] == "admin"
            or app.shares_templates == True
        ]
    return Response(json.dumps(templates), mimetype="application/json")


@app.route("/isard-admin/desktops/templateUpdate/<id>", methods=["GET"])
@login_required
@maintenance
def templateUpdate(id):
    hardware = app.isardapi.get_domain(id)
    return Response(json.dumps(hardware), mimetype="application/json")


@app.route("/isard-admin/desktops/jumperurl/<id>")
@login_required
@maintenance
@ownsid
def jumperurl(id):
    data = app.adminapi.get_jumperurl(id)
    return json.dumps(data), 200, {"Content-Type": "application/json"}


@app.route("/isard-admin/desktops/jumperurl_reset/<id>")
@login_required
@maintenance
@ownsid
def jumperurl_reset(id):
    data = app.adminapi.jumperurl_reset(id)
    return json.dumps(data), 200, {"Content-Type": "application/json"}


@app.route("/isard-admin/desktops/jumperurl_disable/<id>")
@login_required
@maintenance
@ownsid
def jumperurl_disable(id):
    data = app.adminapi.jumperurl_reset(id, disabled=True)
    return json.dumps(data), 200, {"Content-Type": "application/json"}


## Advanced users tags


@app.route("/isard-admin/desktops/tags")
@login_required
@maintenance
@isAdvanced
def groupdesktops(nav="Domains"):
    return render_template(
        "pages/deployment_desktops.html",
        title="Deployments",
        nav="Deployments",
        icon="desktop",
        tags=["prova1", "prova2"],
    )


@app.route("/isard-admin/desktops/tagged", methods=["GET"])
@app.route("/isard-admin/desktops/tagged/<id>", methods=["GET"])
@login_required
@maintenance
@isAdvanced
def advanced_tagged_domains(id=False):
    data = app.isardapi.get_user_tagged_domains(current_user, id)
    return json.dumps(data), 200, {"ContentType": "application/json"}


@app.route("/isard-admin/desktops/usertags", methods=["GET"])
@login_required
@maintenance
@isAdvanced
def advanced_usertags():
    data = app.adminapi.get_user_deployments(current_user.id)
    return json.dumps(data), 200, {"ContentType": "application/json"}
