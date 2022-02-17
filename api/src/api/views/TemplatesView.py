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

from ..libv2.apiv2_exc import *
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
    try:
        template_name = request.form.get("template_name", type=str)
        desktop_id = request.form.get("desktop_id", type=str)
    except Exception as e:
        return (
            json.dumps(
                {
                    "error": "bad_request",
                    "msg": "Incorrect parameters creating Template. exception: "
                    + str(e),
                }
            ),
            400,
            {"Content-Type": "application/json"},
        )

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
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {
                    "error": "bad_request",
                    "msg": "Incorrect access parameters. Check your query.",
                }
            ),
            400,
            {"Content-Type": "application/json"},
        )

    if not ownsDomainId(payload, desktop_id):
        return (
            json.dumps(
                {
                    "error": "forbidden",
                    "msg": "Domain forbidden",
                }
            ),
            403,
            {"Content-Type": "application/json"},
        )
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

    try:
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
    # except UserNotFound:
    #     log.error("Template for user "+user_id+" from desktop "+desktop_id+", user not found")
    #     return json.dumps({"error": "undefined_error","msg":"TemplateNew user not found"}), 404, {'Content-Type': 'application/json'}
    except DesktopNotFound:
        log.error("Template from desktop " + desktop_id + " desktop not found.")
        return (
            json.dumps(
                {
                    "error": "desktop_not_found",
                    "msg": "TemplateNew, desktop not found",
                }
            ),
            404,
            {"Content-Type": "application/json"},
        )
    except DesktopNotCreated:
        log.error("Template from desktop " + desktop_id + " creation failed.")
        return (
            json.dumps(
                {"error": "template_new_not_created", "msg": "TemplateNew not created"}
            ),
            500,
            {"Content-Type": "application/json"},
        )
    except TemplateExists:
        log.error("Template from desktop " + desktop_id + " template id exists.")
        return (
            json.dumps(
                {
                    "error": "template_new_not_created",
                    "msg": "TemplateNew not created: template id exists",
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )
    ### Needs more!
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return (
            json.dumps(
                {
                    "error": "template_new_not_created",
                    "msg": "TemplateNew general exception: " + str(e),
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/template/<template_id>", methods=["GET"])
@has_token
def api_v3_template(payload, template_id=False):
    if id == False:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {
                    "error": "bad_request",
                    "msg": "Incorrect access parameters. Check your query.",
                }
            ),
            400,
            {"Content-Type": "application/json"},
        )

    if not allowedTemplateId(payload, template_id):
        return (
            json.dumps({"error": "forbidden", "msg": "Template access forbidden"}),
            403,
            {"Content-Type": "application/json"},
        )
    try:
        template = templates.Get(template_id)
        if template:
            return json.dumps(template), 200, {"Content-Type": "application/json"}
        return (
            json.dumps({"error": "template_not_found", "msg": "Template not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "get_generic_exception",
                    "msg": "Template general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/template/<template_id>", methods=["DELETE"])
@has_token
def api_v3_template_delete(payload, template_id=False):
    if template_id == False:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {
                    "error": "bad_request",
                    "msg": "Incorrect access parameters. Check your query.",
                }
            ),
            400,
            {"Content-Type": "application/json"},
        )

    if not ownsDomainId(payload, template_id):
        return (
            json.dumps({"error": "forbidden", "msg": "Forbidden domain"}),
            403,
            {"Content-Type": "application/json"},
        )
    try:
        templates.Delete(template_id)
        return json.dumps({}), 200, {"Content-Type": "application/json"}
    except DesktopNotFound:
        log.error("Template delete " + template_id + ", template not found")
        return (
            json.dumps(
                {
                    "error": "template_not_found",
                    "msg": "Template delete id not found",
                }
            ),
            404,
            {"Content-Type": "application/json"},
        )
    except DesktopActionFailed:
        log.error("Template delete " + template_id + ", template delete failed")
        return (
            json.dumps(
                {"error": "generic_error", "msg": "Template delete deleting failed"}
            ),
            500,
            {"Content-Type": "application/json"},
        )
    except DesktopActionTimeout:
        log.error("Template delete " + template_id + ", template delete timeout")
        return (
            json.dumps(
                {"error": "generic_error", "msg": "Template delete deleting timeout"}
            ),
            500,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "TemplateDelete general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )
