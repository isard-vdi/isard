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
    is_admin_or_manager,
    ownsCategoryId,
    ownsUserId,
)


@app.route("/api/v3/admin/jwt/<user_id>", methods=["GET"])
@has_token
def api_v3_admin_jwt(payload, user_id):
    if ownsUserId(payload, user_id):
        return users.Jwt(user_id)
    return (
        json.dumps({"error": "forbidden", "msg": "Forbidden: "}),
        403,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/user/<id>", methods=["GET"])
@has_token
def api_v3_admin_user_exists(payload, id=False):
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

    if not ownsUserId(payload, id):
        return (
            json.dumps({"error": "forbidden", "msg": "Forbidden: "}),
            403,
            {"Content-Type": "application/json"},
        )

    user = users.Exists(id)
    return json.dumps(user), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/users", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_users(payload):
    userslist = users.List()

    if payload["role_id"] == "admin":
        return json.dumps(userslist), 200, {"Content-Type": "application/json"}
    if payload["role_id"] == "manager":
        filtered_users = [
            u for u in userslist if u["category"] == payload["category_id"]
        ]
        return json.dumps(filtered_users), 200, {"Content-Type": "application/json"}
    return (
        json.dumps({"error": "forbidden", "msg": "Forbidden"}),
        403,
        {"Content-Type": "application/json"},
    )


# Update user name
@app.route("/api/v3/admin/user/<id>", methods=["PUT"])
@has_token
def api_v3_admin_user_update(payload, id=False):
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

    if not ownsUserId(payload, id):
        return (
            json.dumps({"error": "forbidden", "msg": "Forbidden: "}),
            403,
            {"Content-Type": "application/json"},
        )
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
                    "error": "bad_request",
                    "msg": "Incorrect access parameters. Check your query. At least one parameter should be specified.",
                }
            ),
            400,
            {"Content-Type": "application/json"},
        )

    users.Update(id, user_name=name, user_email=email, user_photo=photo)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


# Add user
@app.route("/api/v3/admin/user", methods=["POST"])
@has_token
def api_v3_admin_user_insert(payload):
    try:
        # Required
        provider = request.form.get("provider", type=str)
        user_uid = request.form.get("user_uid", type=str)
        user_username = request.form.get("user_username", type=str)
        role_id = request.form.get("role_id", type=str)
        category_id = request.form.get("category_id", type=str)
        group_id = request.form.get("group_id", type=str)

        # Optional
        name = request.form.get("name", user_username, type=str)
        password = request.form.get("password", False, type=str)
        encrypted_password = request.form.get("encrypted_password", False, type=str)
        photo = request.form.get("photo", "", type=str)
        email = request.form.get("email", "", type=str)
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
    if (
        provider == None
        or user_username == None
        or role_id == None
        or category_id == None
        or group_id == None
    ):
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
    if password == None:
        password = False

    if not ownsCategoryId(payload, category_id):
        return (
            json.dumps({"error": "undefined_error", "msg": "Forbidden: "}),
            403,
            {"Content-Type": "application/json"},
        )
    try:
        quotas.UserCreate(category_id, group_id)
    except QuotaCategoryNewUserExceeded:
        log.error(
            "Quota for creating another user in category "
            + category_id
            + " is exceeded"
        )
        return (
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "UserNew category quota for adding user exceeded",
                }
            ),
            507,
            {"Content-Type": "application/json"},
        )
    except QuotaGroupNewUserExceeded:
        log.error(
            "Quota for creating another user in group " + group_id + " is exceeded"
        )
        return (
            json.dumps(
                {
                    "error": "undefined_error",
                    "msg": "UserNew group quota for adding user exceeded",
                }
            ),
            507,
            {"Content-Type": "application/json"},
        )
    except Exception as e:
        error = traceback.format_exc()
        return (
            json.dumps(
                {
                    "error": "generic_error",
                    "msg": "UserNew quota check general exception: " + error,
                }
            ),
            500,
            {"Content-Type": "application/json"},
        )

    user_id = users.Create(
        provider,
        category_id,
        user_uid,
        user_username,
        name,
        role_id,
        group_id,
        password,
        encrypted_password,
        photo,
        email,
    )
    return json.dumps({"id": user_id}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/user/<user_id>", methods=["DELETE"])
@has_token
def api_v3_admin_user_delete(payload, user_id):

    if not ownsUserId(payload, user_id):
        return (
            json.dumps({"error": "undefined_error", "msg": "Forbidden: "}),
            403,
            {"Content-Type": "application/json"},
        )

    users.Delete(user_id)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/templates", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_templates(payload):
    return (
        json.dumps(users.Templates(payload)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/user/<id>/templates", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_user_templates(payload, id=False):
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

    if not ownsUserId(payload, id):
        return (
            json.dumps({"error": "undefined_error", "msg": "Forbidden: "}),
            403,
            {"Content-Type": "application/json"},
        )

    templates = users.Templates(id)
    dropdown_templates = [
        {
            "id": t["id"],
            "name": t["name"],
            "icon": t["icon"],
            "image": "",
            "description": t["description"],
        }
        for t in templates
    ]
    return json.dumps(dropdown_templates), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/user/<user_id>/desktops", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_user_desktops(payload, user_id=None):
    if not user_id:
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

    if not ownsUserId(payload, user_id):
        return (
            json.dumps({"error": "undefined_error", "msg": "Forbidden: "}),
            403,
            {"Content-Type": "application/json"},
        )

    desktops = users.Desktops(user_id)
    return (
        json.dumps(users.Desktops(user_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/category/<category_id>", methods=["GET"])
@is_admin
def api_v3_admin_category(payload, category_id):
    if not ownsCategoryId(payload, category_id):
        return (
            json.dumps({"error": "undefined_error", "msg": "Forbidden: "}),
            403,
            {"Content-Type": "application/json"},
        )

    data = users.CategoryGet(category_id)
    return json.dumps(data), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/category", methods=["POST"])
@is_admin
def api_v3_admin_category_insert(payload):
    try:
        # Required
        category_name = request.form.get("category_name", type=str)

        # Optional
        frontend = request.form.get("frontend", False)
        if frontend == "False":
            frontend = False
        if frontend == "True":
            frontend = True
        group_name = request.form.get("group_name", False)
        category_limits = request.form.get("category_limits", False)
        if category_limits == "False":
            category_limits = False
        if category_limits != False:
            category_limits = json.loads(category_limits)
        category_quota = request.form.get("category_quota", False)
        if category_quota == "False":
            category_quota = False
        if category_quota != False:
            category_quota = json.loads(category_quota)
        group_quota = request.form.get("group_quota", False)
        if group_quota == "False":
            group_quota = False
        if group_quota != False:
            group_quota = json.loads(group_quota)

    ## We should check here if limits and quotas have a correct dict schema

    ##
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
    if category_name == None:
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

    category_id = users.CategoryCreate(
        category_name,
        frontend=frontend,
        group_name=group_name,
        category_limits=category_limits,
        category_quota=category_quota,
        group_quota=group_quota,
    )
    return (
        json.dumps({"id": category_id}),
        200,
        {"Content-Type": "application/json"},
    )


# Add group
@app.route("/api/v3/admin/group", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_group_insert(payload):
    try:
        # Required
        category_id = request.form.get("category_id", type=str)
        group_name = request.form.get("group_name", type=str)

        # Optional
        category_limits = request.form.get("category_limits", False)
        if category_limits == "False":
            category_limits = False
        if category_limits != False:
            category_limits = json.loads(category_limits)
        category_quota = request.form.get("category_quota", False)
        if category_quota == "False":
            category_quota = False
        if category_quota != False:
            category_quota = json.loads(category_quota)
        group_quota = request.form.get("group_quota", False)
        if group_quota == "False":
            group_quota = False
        if group_quota != False:
            group_quota = json.loads(group_quota)

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
    if category_id == None:
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

    if not ownsCategoryId(payload, category_id):
        return (
            json.dumps({"error": "undefined_error", "msg": "Forbidden: "}),
            403,
            {"Content-Type": "application/json"},
        )
    ## We should check here if limits and quotas have a correct dict schema

    ##

    group_id = users.GroupCreate(
        category_id,
        group_name,
        category_limits=category_limits,
        category_quota=category_quota,
        group_quota=group_quota,
    )
    return json.dumps({"id": group_id}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/categories", methods=["GET"])
@app.route("/api/v3/admin/categories/<frontend>", methods=["GET"])
@is_admin
def api_v3_admin_categories(payload, frontend=False):
    if not frontend:
        return (
            json.dumps(users.CategoriesGet()),
            200,
            {"Content-Type": "application/json"},
        )
    else:
        return (
            json.dumps(users.CategoriesFrontendGet()),
            200,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/admin/category/<category_id>", methods=["DELETE"])
@is_admin
def api_v3_admin_category_delete(category_id, payload):
    return (
        json.dumps(users.CategoryDelete(category_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/groups", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_groups(payload):
    groups = users.GroupsGet()
    if payload["role_id"] == "manager":
        groups = [g for g in groups if g["parent_category"] == payload["category_id"]]
    return json.dumps(groups), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/group/<group_id>", methods=["DELETE"])
@is_admin_or_manager
def api_v3_admin_group_delete(group_id, payload):
    if payload["role_id"] == "manager" and not ownsCategoryId(g["parent_category"]):
        return (
            json.dumps({"error": "forbidden", "msg": "Forbidden"}),
            403,
            {"Content-Type": "application/json"},
        )

    return (
        json.dumps(users.GroupDelete(group_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/user/<user_id>/vpn/<kind>/<os>", methods=["GET"])
@app.route("/api/v3/admin/user/<user_id>/vpn/<kind>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_user_vpn(payload, user_id, kind, os=False):
    if not ownsUserId(payload, user_id):
        return (
            json.dumps({"error": "undefined_error", "msg": "Forbidden: "}),
            403,
            {"Content-Type": "application/json"},
        )
    if not os and kind != "config":
        return (
            json.dumps({"error": "undefined_error", "msg": "UserVpn: no OS supplied"}),
            401,
            {"Content-Type": "application/json"},
        )

    vpn_data = vpn.vpn_data("users", kind, os, user_id)

    if vpn_data:
        return json.dumps(vpn_data), 200, {"Content-Type": "application/json"}
    else:
        return (
            json.dumps({"error": "undefined_error", "msg": "UserVpn no VPN data"}),
            401,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/admin/secret", methods=["POST"])
@is_admin
def api_v3_admin_secret(payload):
    try:
        # Required
        kid = request.form.get("kid", type=str)
        description = request.form.get("description", "")
        role_id = request.form.get("role_id", type=str)
        category_id = request.form.get("category_id", type=str)
        domain = request.form.get("domain", type=str)

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

    if role_id == None or domain == None or kid == None or category_id == None:
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

    secret = users.Secret(kid, description, role_id, category_id, domain)
    return json.dumps({"secret": secret}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/secret/<kid>", methods=["DELETE"])
@is_admin
def api_v3_admin_secret_delete(payload, kid):
    users.SecretDelete(kid)
    return json.dumps({}), 200, {"Content-Type": "application/json"}
