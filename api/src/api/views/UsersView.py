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
from rethinkdb import RethinkDB

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.api_exceptions import Error
from ..libv2.quotas import Quotas

quotas = Quotas()
from ..libv2.flask_rethink import RDB

r = RethinkDB()
db = RDB(app)
db.init_app(app)

from ..libv2.api_users import ApiUsers, check_category_domain

users = ApiUsers()

from ..libv2.isardVpn import isardVpn

vpn = isardVpn()

from .decorators import has_token, is_admin, is_auto_register, is_register

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
    user = users.Get(payload["user_id"])
    return json.dumps(user), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/user/auto-register", methods=["POST"])
@is_auto_register
def api_v3_user_auto_register(payload):
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


@app.route("/api/v3/user/register", methods=["POST"])
@is_register
def api_v3_user_register(payload):
    try:
        code = request.form.get("code", type=str)
    except:
        raise Error(
            "bad_request",
            "New register code bad body data",
            traceback.format_exc(),
        )

    data = users.CodeSearch(code)
    if payload["category_id"] != data["category"]:
        raise Error(
            "bad_request",
            "Requested register code not in the category selected",
            traceback.format_exc(),
        )

    check_category_domain(data.get("category"), payload["email"].split("@")[-1])

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


@app.route("/api/v3/user/config", methods=["GET"])
@has_token
def api_v3_user_config(payload):
    return json.dumps(users.Config(payload)), 200, {"Content-Type": "application/json"}


# Check from isard-guac if the user owns the ip
@app.route("/api/v3/user/owns_desktop", methods=["GET"])
@has_token
def api_v3_user_owns_desktop(payload):
    if payload.get("desktop_id"):
        return json.dumps({}), 200, {"Content-Type": "application/json"}
    else:
        try:
            ip = request.form.get("ip", False)
        except:
            raise Error("bad_request", "Missing parameters.", traceback.format_exc())

        if ip == False:
            raise Error(
                "bad_request",
                "Incorrect access parameters",
                traceback.format_exc(),
            )
        users.OwnsDesktop(payload["user_id"], ip)
        return json.dumps({}), 200, {"Content-Type": "application/json"}


# Update user name
@app.route("/api/v3/user", methods=["PUT"])
@has_token
def api_v3_user_update(payload):
    try:
        name = request.form.get("name", None)
        email = request.form.get("email", None)
        photo = request.form.get("photo", None)
        password = request.form.get("password", None)
    except:
        raise Error("bad_request", "Update user bad body data", traceback.format_exc())
    if not name and not email and not photo and not password:
        raise Error(
            "bad_request",
            "Update user incorrect body data",
            traceback.format_exc(),
        )

    users.Update(
        payload["user_id"], name=name, email=email, photo=photo, password=password
    )
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/user", methods=["DELETE"])
@has_token
def api_v3_user_delete(payload):
    users.Delete(payload["user_id"])
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/user/templates", methods=["GET"])
@has_token
def api_v3_user_templates(payload):
    with app.app_context():
        group = r.table("groups").get(payload["group_id"])["uid"].run(db.conn)
    if group == None:
        raise Error("not_found", "Group not found", traceback.format_exc())
    dropdown_templates = [
        {
            "id": t["id"],
            "name": t["name"],
            "category": t["category"],
            "group": group,
            "user_id": t["user"],
            "icon": t["icon"],
            "image": t["image"],
            "allowed": t["allowed"],
            "description": t["description"],
            "enabled": t["enabled"],
        }
        for t in users.Templates(payload)
    ]
    return json.dumps(dropdown_templates), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/user/templates_allowed", methods=["GET"])
@has_token
def api_v3_user_templates_allowed(payload):
    templates = users.TemplatesAllowed(payload)
    dropdown_templates = [
        {
            "id": t["id"],
            "name": t["name"],
            "category": t["category"],
            "category_name": t["category_name"],
            "group": t["group"],
            "group_name": t["group_name"],
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


@app.route("/api/v3/user/desktops", methods=["GET"])
@has_token
def api_v3_user_desktops(payload):
    desktops = users.Desktops(payload["user_id"])
    return json.dumps(desktops), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/user/desktop/<desktop_id>", methods=["GET"])
@has_token
def api_v3_user_desktop(payload, desktop_id):
    return (
        json.dumps(users.Desktop(desktop_id, payload["user_id"])),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/user/vpn/<kind>/<os>", methods=["GET"])
@app.route("/api/v3/user/vpn/<kind>", methods=["GET"])
# kind = config,install
# os =
@has_token
def api_v3_user_vpn(payload, kind, os=False):
    if not os and kind != "config":
        raise Error("bad_request", "User Vpn incorrect data", traceback.format_exc())

    vpn_data = vpn.vpn_data("users", kind, os, payload["user_id"])
    return json.dumps(vpn_data), 200, {"Content-Type": "application/json"}
