# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import time

import rethinkdb as r

#!/usr/bin/env python
# coding=utf-8
from flask import (
    Response,
    redirect,
    render_template,
    request,
    stream_with_context,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from webapp import app

from ..lib.flask_rethink import RethinkDB
from ..lib.log import *

db = RethinkDB(app)
db.init_app(app)

from .decorators import checkRole, ownsid


@app.route("/isard-admin/templates")
@login_required
@checkRole
def templates():
    return render_template("pages/templates.html", nav="Templates")


@app.route("/isard-admin/template/get/")
@login_required
def templates_get():
    return (
        json.dumps(app.isardapi.get_user_templates(current_user.id)),
        200,
        {"Content-Type": "application/json"},
    )
