# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json

from flask import render_template
from flask_login import login_required

from webapp import app

from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

import tempfile

from .decorators import isAdminManager


@app.route("/isard-admin/admin/isard-admin/media", methods=["POST", "GET"])
@login_required
@isAdminManager
def admin_media():
    return render_template("admin/pages/media.html", nav="Media")
