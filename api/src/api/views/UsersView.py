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

from flask import jsonify, request

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.apiv2_exc import *
from ..libv2.quotas import Quotas
from ..libv2.quotas_exc import *

quotas = Quotas()

from ..libv2.api_users import ApiUsers, check_category_domain

users = ApiUsers()

from ..libv2.isardVpn import isardVpn

vpn = isardVpn()

from .decorators import (
    has_token,
    is_admin,
    is_auto_register,
    is_register,
    ownsCategoryId,
    ownsUserId,
)

"""
Users jwt endpoints
"""


@app.route("/api/v3/jwt", methods=["GET"])
@has_token
def api_v3_jwt(payload):
    ### Refreshes it's own token with new one.
    return users.Jwt(payload["user_id"])


@app.route("/api/v3/user", methods=["GET"])
@has_token
def api_v3_user_exists(payload):
    try:
        user = users.Exists(payload["user_id"])
        return json.dumps(user), 200, {"Content-Type": "application/json"}
    except UserNotFound:
        log.error("User " + id + " not in database.")
        return (
            json.dumps(
                {"error": "undefined_error", "msg": "User not exists in database"}
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
                    "msg": "UserExists general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/user/auto-register", methods=["POST"])
@is_auto_register
def api_v3_user_auto_register(payload):
    try:
        user_id = users.Create(
            payload["provider"],
            payload["category_id"],
            payload["user_id"],
            payload["username"],
            payload["name"],
            payload["role"],
            payload["group"],
            photo=payload["photo"],
            email=payload["email"],
        )
        return json.dumps({"id": user_id}), 200, {"Content-Type": "application/json"}
    except UserExists:
        return json.dumps(payload), 200, {"Content-Type": "application/json"}
    except RoleNotFound:
        log.error("Role " + payload["role"] + " not found.")
        return (
            json.dumps({"error": "undefined_error", "msg": "Role not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except CategoryNotFound:
        log.error("Category " + payload["category_id"] + " not found.")
        return (
            json.dumps({"error": "undefined_error", "msg": "Category not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except GroupNotFound:
        log.error("Group " + payload["group"] + " not found.")
        return (
            json.dumps({"error": "undefined_error", "msg": "Group not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except NewUserNotInserted:
        log.error(
            "User " + payload["username"] + " could not be inserted into database."
        )
        return (
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "User could not be inserted into database. Already exists!",
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
                    "msg": "UserUpdate general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/user/register", methods=["POST"])
@is_register
def api_v3_user_register(payload):
    try:
        code = request.form.get("code", type=str)
        # domain = request.form.get("email").split("@")[-1]
    except Exception as e:
        return (
            json.dumps(
                {"error": "undefined_error", "msg": "Incorrect access. exception: " + e}
            ),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        data = users.CodeSearch(code)
        if payload["category_id"] != data["category"]:
            log.error(
                "Code "
                + code
                + " it's in a category not requested by user register form."
            )
            return (
                json.dumps(
                    {
                        "error": "undefined_error",
                        "msg": "Code "
                        + code
                        + " it's in a category not requested by user register form.",
                    }
                ),
                404,
                {"Content-Type": "application/json"},
            )
        check_category_domain(data.get("category"), payload["category_id"])
    except CodeNotFound:
        log.error("Code not in database.")
        return (
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "Code " + code + " not exists in database",
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
                    "msg": "Register general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )

    try:
        user_id = users.Create(
            payload["provider"],
            payload["category_id"],
            payload["user_id"],
            payload["username"],
            payload["name"],
            data.get("role"),
            data.get("group"),
            photo=payload["photo"],
            email=payload["email"],
        )
        return json.dumps({"id": user_id}), 200, {"Content-Type": "application/json"}
    except UserExists:
        return json.dumps(payload), 200, {"Content-Type": "application/json"}
    except RoleNotFound:
        log.error("Role " + data.get("role") + " not found.")
        return (
            json.dumps({"error": "undefined_error", "msg": "Role not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except CategoryNotFound:
        log.error("Category " + payload["category_id"] + " not found.")
        return (
            json.dumps({"error": "undefined_error", "msg": "Category not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except GroupNotFound:
        log.error("Group " + data.get("group") + " not found.")
        return (
            json.dumps({"error": "undefined_error", "msg": "Group not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except NewUserNotInserted:
        log.error(
            "User " + payload["username"] + " could not be inserted into database."
        )
        return (
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "User could not be inserted into database. Already exists!",
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
                    "msg": "UserUpdate general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )


# Check from isard-guac if the user owns the ip
@app.route("/api/v3/user/owns_desktop", methods=["GET"])
@has_token
def api_v3_user_owns_desktop(payload):
    try:
        ip = request.form.get("ip", False)
    except Exception as e:
        return (
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "Incorrect access. exception: " + str(e),
                }
            ),
            401,
            {"Content-Type": "application/json"},
        )

    if ip == False:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "Incorrect access parameters. Check your query. At least one parameter should be specified.",
                }
            ),
            401,
            {"Content-Type": "application/json"},
        )
    try:
        users.OwnsDesktop(payload["user_id"], ip)

        return json.dumps({}), 200, {"Content-Type": "application/json"}
    except DesktopNotFound:  # If not owns
        log.error("User " + payload["username"] + " not owns the desktop ip.")
        return (
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "User " + payload["username"] + " not owns the desktop ip",
                }
            ),
            401,
            {"Content-Type": "application/json"},
        )
    except:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "OwnsDesktop general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )


# Update user name
@app.route("/api/v3/user", methods=["PUT"])
@has_token
def api_v3_user_update(payload):
    try:
        name = request.form.get("name", "")
        email = request.form.get("email", "")
        photo = request.form.get("photo", "")
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "Incorrect access. exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )

    if name == False and email == False and photo == False:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "Incorrect access parameters. Check your query. At least one parameter should be specified.",
                }
            ),
            401,
            {"Content-Type": "application/json"},
        )
    try:
        users.Update(
            payload["user_id"], user_name=name, user_email=email, user_photo=photo
        )
        return json.dumps({}), 200, {"Content-Type": "application/json"}
    except UpdateFailed:
        log.error("User " + id + " update failed.")
        return (
            json.dumps({"error": "undefined_error", "msg": "User update failed"}),
            404,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "UserUpdate general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/user", methods=["DELETE"])
@has_token
def api_v3_user_delete(payload):
    try:
        users.Delete(payload["user_id"])
        return json.dumps({}), 200, {"Content-Type": "application/json"}
    except UserNotFound:
        log.error("User delete " + payload["user_id"] + ", user not found")
        return (
            json.dumps({"error": "undefined_error", "msg": "User delete id not found"}),
            404,
            {"Content-Type": "application/json"},
        )
    except UserDeleteFailed:
        log.error("User delete " + payload["user_id"] + ", user delete failed")
        return (
            json.dumps({"error": "undefined_error", "msg": "User delete failed"}),
            404,
            {"Content-Type": "application/json"},
        )
    except DesktopDeleteFailed:
        log.error("User delete for user " + payload["user_id"] + ", user delete failed")
        return (
            json.dumps(
                {"error": "undefined_error", "msg": "User delete, user deleting failed"}
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
                    "msg": "UserDelete general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/user/templates", methods=["GET"])
@has_token
def api_v3_user_templates(payload):
    if id == False:
        log.error("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "Incorrect access parameters. Check your query.",
                }
            ),
            401,
            {"Content-Type": "application/json"},
        )

    try:
        templates = users.Templates(payload)
        dropdown_templates = [
            {
                "id": t["id"],
                "name": t["name"],
                "category": t["category"],
                "group": t["group"].split("-")[1],
                "user_id": t["user"],
                "user_name": t["username"],
                "icon": t["icon"],
                "image": t["image"],
                "editable": t["editable"],
                "description": t["description"],
            }
            for t in templates
        ]
        return json.dumps(dropdown_templates), 200, {"Content-Type": "application/json"}
    except UserNotFound:
        log.error("User " + payload["user_id"] + " not in database.")
        return (
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "UserTemplates: User not exists in database",
                }
            ),
            404,
            {"Content-Type": "application/json"},
        )
    except UserTemplatesError:
        log.error("Template list for user " + payload["user_id"] + " failed.")
        return (
            json.dumps(
                {"error": "undefined_error", "msg": "UserTemplates: list error"}
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
                    "msg": "UserTemplates general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/user/desktops", methods=["GET"])
@has_token
def api_v3_user_desktops(payload):
    try:
        desktops = users.Desktops(payload["user_id"])
        return json.dumps(desktops), 200, {"Content-Type": "application/json"}
    except:
        raise


@app.route("/api/v3/user/desktop/<desktop_id>", methods=["GET"])
@has_token
def api_v3_user_desktop(payload, desktop_id):
    try:
        desktop = users.Desktop(desktop_id, payload["user_id"])
        desktop_dict = {
            "id": desktop["id"],
            "name": desktop["name"],
            "state": desktop["status"],
            "type": desktop["type"],
            "template": desktop["from_template"],
            "viewers": desktop["viewers"],
            "icon": desktop["icon"],
            "image": desktop["image"],
            "description": desktop["description"],
            "ip": desktop.get("ip"),
        }
        return json.dumps(desktop_dict), 200, {"Content-Type": "application/json"}
    except:
        raise


@app.route("/api/v3/user/vpn/<kind>/<os>", methods=["GET"])
@app.route("/api/v3/user/vpn/<kind>", methods=["GET"])
# kind = config,install
# os =
@has_token
def api_v3_user_vpn(payload, kind, os=False):
    if not os and kind != "config":
        return (
            json.dumps({"error": "bad_request", "msg": "UserVpn: no OS supplied"}),
            400,
            {"Content-Type": "application/json"},
        )

    vpn_data = vpn.vpn_data("users", kind, os, payload["user_id"])

    if vpn_data:
        return json.dumps(vpn_data), 200, {"Content-Type": "application/json"}
    else:
        return (
            json.dumps({"error": "vpn_not_found", "msg": "UserVpn no VPN data"}),
            404,
            {"Content-Type": "application/json"},
        )
