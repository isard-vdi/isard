# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8

from flask import render_template
from flask_login import login_required

from ...auth.authentication import *
from .decorators import isAdminManager


@app.route("/isard-admin/admin/users", methods=["POST", "GET"])
@login_required
@isAdminManager
def admin_users():
    return render_template("admin/pages/users.html", nav="Users")
