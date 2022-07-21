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

from ..libv2.api_users import ApiUsers

users = ApiUsers()

from ..libv2.api_templates import ApiTemplates

templates = ApiTemplates()

from ..libv2.validators import _validate_item
from .decorators import allowedTemplateId, has_token, ownsDomainId


@app.route("/api/v3/template", methods=["POST"])
@has_token
def api_v3_template_new(payload):
    quotas.TemplateCreate(payload)
    data = request.get_json(force=True)
    data["user_id"] = payload["user_id"]
    data = _validate_item("template", data)
    ownsDomainId(payload, data["desktop_id"])
    if data["name"] == None or data["desktop_id"] == None:
        raise Error(
            "bad_request",
            "New template bad body data",
            traceback.format_exc(),
        )
    template_id = templates.New(
        payload["user_id"],
        data["template_id"],
        data["name"],
        data["desktop_id"],
        data["allowed"],
        description=data["description"],
        enabled=data["enabled"],
    )
    return (
        json.dumps({"id": template_id}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/template/<template_id>", methods=["GET"])
@has_token
def api_v3_template(payload, template_id):
    allowedTemplateId(payload, template_id)
    return (
        json.dumps(templates.Get(template_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/template/<template_id>", methods=["DELETE"])
@has_token
def api_v3_template_delete(payload, template_id):
    ownsDomainId(payload, template_id)
    templates.Delete(template_id)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


# Disable or enable template
@app.route("/api/v3/template/update", methods=["PUT"])
@has_token
def api_v3_template_update(payload):
    data = request.get_json(force=True)
    template_id = data.pop("id")
    ownsDomainId(payload, template_id)
    return (
        json.dumps(templates.UpdateTemplate(template_id, data)),
        200,
        {"Content-Type": "application/json"},
    )
