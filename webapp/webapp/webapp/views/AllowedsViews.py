# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

from flask import request
from flask_login import current_user, login_required

from webapp import app

from ..lib.flask_rethink import RethinkDB
from ..lib.log import *
from .decorators import maintenance, ownsid, ownsidortag

db = RethinkDB(app)
db.init_app(app)

import json

from ..lib.quotas import QuotaLimits

quotas = QuotaLimits()

# Will get allowed hardware quota max resources for current_user
@app.route("/isard-admin/<kind>/quotamax", methods=["GET"])
@app.route("/isard-admin/<kind>/quotamax/<id>", methods=["GET"])
@login_required
@maintenance
def user_quota_max(kind, id=False):
    if kind == "user":
        if id == False:
            id = current_user.id
        return json.dumps(quotas.get_user(id))

    if kind == "category":
        if id == False:
            id = current_user.category
        return json.dumps(quotas.get_category(id))

    if kind == "group":
        if id == False:
            id = current_user.group
        return json.dumps(quotas.get_group(id))


@app.route("/isard-admin/domains/removable", methods=["POST"])
@login_required
@maintenance
@ownsid
def domain_removable():
    if request.method == "POST":
        return json.dumps(
            app.adminapi.is_template_removable(
                request.get_json(force=True)["id"], current_user.id
            )
        )
    return json.dumps("Could not check."), 500, {"Content-Type": "application/json"}
