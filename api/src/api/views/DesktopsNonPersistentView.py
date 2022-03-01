# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import os
import sys
import time
import traceback
from uuid import uuid4

from flask import request

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.apiv2_exc import *
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_desktops_nonpersistent import ApiDesktopsNonPersistent

desktops = ApiDesktopsNonPersistent()

from .decorators import allowedTemplateId, has_token, is_admin, ownsDomainId


@app.route("/api/v3/desktop", methods=["POST"])
@has_token
def api_v3_desktop_new(payload):
    try:
        user_id = payload["user_id"]
        template_id = request.form.get("template", type=str)
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "bad_request",
                    "msg": "Incorrect access. Exception: " + error,
                }
            ),
            400,
            {"Content-Type": "application/json"},
        )
    if user_id == None or template_id == None:
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
            json.dumps({"error": "forbidden", "msg": "Forbidden template"}),
            403,
            {"Content-Type": "application/json"},
        )
    # Leave only one nonpersistent desktop from this template
    try:
        desktops.DeleteOthers(user_id, template_id)

    except DesktopNotFound:
        quotas.DesktopCreateAndStart(user_id)
    except DesktopNotStarted:
        quotas.DesktopStart(user_id)

    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "DesktopNew previous checks general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )

    # So now we have checked if desktop exists and if we can create and/or start it

    try:
        desktop_id = desktops.New(user_id, template_id)
        return json.dumps({"id": desktop_id}), 200, {"Content-Type": "application/json"}
    except UserNotFound:
        log.error(
            "Desktop for user "
            + user_id
            + " from template "
            + template_id
            + ", user not found"
        )
        return (
            json.dumps(
                {
                    "error": "user_not_found",
                    "msg": "DesktopNew user not found",
                }
            ),
            404,
            {"Content-Type": "application/json"},
        )
    except TemplateNotFound:
        log.error(
            "Desktop for user "
            + user_id
            + " from template "
            + template_id
            + " template not found."
        )
        return (
            json.dumps(
                {
                    "error": "template_not_found",
                    "msg": "DesktopNew template not found",
                }
            ),
            404,
            {"Content-Type": "application/json"},
        )
    except DesktopNotCreated:
        log.error(
            "Desktop for user "
            + user_id
            + " from template "
            + template_id
            + " creation failed."
        )
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "DesktopNew not created",
                }
            ),
            404,
            {"Content-Type": "application/json"},
        )
    except DesktopActionTimeout:
        log.error(
            "Desktop for user "
            + user_id
            + " from template "
            + template_id
            + " start timeout."
        )
        return (
            json.dumps(
                {"error": "desktop_start_timeout", "msg": "DesktopNew start timeout"}
            ),
            504,
            {"Content-Type": "application/json"},
        )
    except DesktopActionFailed:
        log.error(
            "Desktop for user "
            + user_id
            + " from template "
            + template_id
            + " start failed."
        )
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "DesktopNew start failed",
                }
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
                    "msg": "DesktopNew general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/desktop/<desktop_id>", methods=["DELETE"])
@has_token
def api_v3_desktop_delete(payload, desktop_id=False):
    if desktop_id == False:
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

    ownsDomainId(payload, desktop_id)
    try:
        desktops.Delete(desktop_id)
        return json.dumps({}), 200, {"Content-Type": "application/json"}
    except DesktopNotFound:
        log.error("Desktop delete " + desktop_id + ", desktop not found")
        return (
            json.dumps(
                {"error": "desktop_not_found", "msg": "Desktop delete id not found"}
            ),
            404,
            {"Content-Type": "application/json"},
        )
    except DesktopDeleteFailed:
        log.error("Desktop delete " + desktop_id + ", desktop delete failed")
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "Desktop delete, deleting failed",
                }
            ),
            404,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "DesktopDelete general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )
