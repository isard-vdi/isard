# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json

from flask import (
    Response,
    after_this_request,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user
from werkzeug.utils import secure_filename

from webapp import app

from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

import os
import tempfile

from .decorators import isAdmin, isAdminManager


@app.route("/isard-admin/admin/isard-admin/media", methods=["POST", "GET"])
@login_required
@isAdminManager
def admin_media():
    return render_template("admin/pages/media.html", nav="Media")


@app.route("/isard-admin/admin/isard-admin/media/download/<filename>", methods=["GET"])
# ~ @login_required
# ~ @isAdmin
def admin_media_download(filename):
    with open("./uploads/" + filename, "rb") as isard_file:
        data = isard_file.read()

    @after_this_request
    def remove_file(response):
        try:
            os.remove("./uploads/" + filename)
        except Exception as error:
            print("Error removing or closing downloaded file handle", error)
        return response

    return Response(
        data,
        mimetype="application/octet-stream",
        headers={"Content-Disposition": "attachment;filename=" + filename},
    )
