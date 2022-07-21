# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import rethinkdb as r

#!/usr/bin/env python
# coding=utf-8
from flask import Response, render_template
from flask_login import current_user, login_required

from webapp import app

from ..lib.flask_rethink import RethinkDB
from ..lib.log import *
from .decorators import isAdvanced, maintenance

db = RethinkDB(app)
db.init_app(app)

import json


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


@app.route("/isard-admin/desktops/templateUpdate/<id>", methods=["GET"])
@login_required
@maintenance
def templateUpdate(id):
    hardware = app.isardapi.get_domain(id)
    return Response(json.dumps(hardware), mimetype="application/json")


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
