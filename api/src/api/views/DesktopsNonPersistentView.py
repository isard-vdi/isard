# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import traceback

from flask import request

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.api_exceptions import Error
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_desktops_nonpersistent import ApiDesktopsNonPersistent

desktops = ApiDesktopsNonPersistent()

from .decorators import allowedTemplateId, has_token


@app.route("/api/v3/desktop", methods=["POST"])
@has_token
def api_v3_desktop_new(payload):
    try:
        user_id = payload["user_id"]
        template_id = request.form.get("template", type=str)
    except:
        raise Error("bad_request", "New desktop bad body data", traceback.format_exc())

    if user_id == None or template_id == None:
        raise Error(
            "bad_request",
            "New desktop missing body data",
            traceback.format_exc(),
            description_code="missing_required_data",
        )

    allowedTemplateId(payload, template_id)

    # Leave only one nonpersistent desktop from this template
    desktops.DeleteOthers(user_id, template_id)

    # So now we have checked if desktop exists and if we can create and/or start it
    return (
        json.dumps({"id": desktops.New(user_id, template_id)}),
        200,
        {"Content-Type": "application/json"},
    )
