# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import os
import sys
import time
from uuid import uuid4

from flask import request

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.api_exceptions import Error
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_users import ApiUsers

users = ApiUsers()

# from ..libv2.api_desktops import ApiDesktops
# desktops = ApiDesktops()

from ..libv2.api_templates import ApiTemplates

templates = ApiTemplates()

from .decorators import allowedTemplateId, has_token, is_admin, ownsDomainId


@app.route("/api/v3/template", methods=["POST"])
@has_token
def api_v3_template_new(payload):
    template_name = request.form.get("template_name", type=str)
    desktop_id = request.form.get("desktop_id", type=str)

    allowed_roles = request.form.getlist("allowed_roles")
    allowed_roles = False if allowed_roles is None else allowed_roles
    allowed_categories = request.form.getlist("allowed_categories", type=str)
    allowed_categories = False if allowed_categories is None else allowed_categories
    allowed_groups = request.form.getlist("allowed_groups", type=str)
    allowed_groups = False if allowed_groups is None else allowed_groups
    allowed_users = request.form.getlist("allowed_users", type=str)
    allowed_users = False if allowed_users is None else allowed_users

    # if user_id == None or
    if template_name == None or desktop_id == None:
        raise Error(
            "bad_request", "New template bad body data", traceback.format_stack()
        )

    ownsDomainId(payload, desktop_id)
    # try:
    #     quotas.DesktopCreate(user_id)
    # except QuotaUserNewDesktopExceeded:
    #     log.error("Quota for user "+user_id+" for creating another desktop is exceeded")
    #     return json.dumps({"error": "undefined_error","msg":"TemplateNew user category quota CREATE exceeded"}), 507, {'Content-Type': 'application/json'}
    # except QuotaGroupNewDesktopExceeded:
    #     log.error("Quota for user "+user_id+" group for creating another desktop is exceeded")
    #     return json.dumps({"error": "undefined_error","msg":"TemplateNew user category quota CREATE exceeded"}), 507, {'Content-Type': 'application/json'}
    # except QuotaCategoryNewDesktopExceeded:
    #     log.error("Quota for user "+user_id+" category for creating another desktop is exceeded")
    #     return json.dumps({"error": "undefined_error","msg":"TemplateNew user category quota CREATE exceeded"}), 507, {'Content-Type': 'application/json'}
    # except Exception as e:
    #     exc_type, exc_obj, exc_tb = sys.exc_info()
    #     fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
    #     log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
    #     return json.dumps({"error": "undefined_error","msg":"TemplateNew quota check general exception: " + str(e) }), 401, {'Content-Type': 'application/json'}

    template_id = templates.New(
        template_name,
        desktop_id,
        allowed_roles=allowed_roles,
        allowed_categories=allowed_categories,
        allowed_groups=allowed_groups,
        allowed_users=allowed_users,
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
