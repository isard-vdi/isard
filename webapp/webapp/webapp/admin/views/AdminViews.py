# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json
import time

from flask import render_template, request
from flask_login import login_required

from webapp import app

from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

from ...lib.flask_rethink import RethinkDB

db = RethinkDB(app)
db.init_app(app)

from .decorators import isAdmin, isAdminManager

"""
LANDING ADMIN PAGE
"""


@app.route("/isard-admin/admin")
@login_required
@isAdmin
def admin():
    return render_template(
        "admin/pages/hypervisors.html",
        title="Hypervisors",
        header="Hypervisors",
        nav="Hypervisors",
    )


"""
CONFIG
"""


@app.route("/isard-admin/admin/config", methods=["GET", "POST"])
@login_required
@isAdminManager
def admin_config():
    if request.method == "POST":
        return (
            json.dumps(app.adminapi.get_admin_config(1)),
            200,
            {"Content-Type": "application/json"},
        )
    return render_template("admin/pages/config.html", nav="Config")


"""
BACKUP & RESTORE
"""


@app.route("/isard-admin/admin/backup/upload", methods=["POST"])
@login_required
@isAdmin
def admin_backup_upload():
    for f in request.files:
        app.adminapi.upload_backup(request.files[f])
    return json.dumps("Updated"), 200, {"Content-Type": "application/json"}
