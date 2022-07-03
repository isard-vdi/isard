# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import os
import time
import traceback
from uuid import uuid4

from flask import jsonify, request

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.api_admin import admin_table_delete, admin_table_insert, admin_table_update
from ..libv2.api_exceptions import Error
from ..libv2.api_users import ApiUsers, Password, check_category_domain
from ..libv2.helpers import _check
from ..libv2.quotas import Quotas
from ..libv2.validators import _validate_item

quotas = Quotas()


users = ApiUsers()

from ..libv2.isardVpn import isardVpn

vpn = isardVpn()

from .decorators import (
    has_token,
    is_admin,
    is_admin_or_manager,
    itemExists,
    ownsCategoryId,
    ownsDomainId,
    ownsUserId,
)


@app.route("/api/v3/admin/jwt/<user_id>", methods=["GET"])
@has_token
def api_v3_admin_jwt(payload, user_id):
    ownsUserId(payload, user_id)
    return users.Jwt(user_id)


@app.route("/api/v3/admin/user/<user_id>", methods=["GET"])
@has_token
def api_v3_admin_user_exists(payload, user_id):
    ownsUserId(payload, user_id)
    return json.dumps(users.Get(user_id)), 200, {"Content-Type": "application/json"}


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


# Update user
@app.route("/api/v3/admin/user/<id>", methods=["PUT"])
@has_token
def api_v3_admin_user_update(payload, id=False):

    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )

    ownsUserId(payload, id)
    ownsCategoryId(payload, data["category"])
    itemExists("categories", data["category"])
    itemExists("groups", data["group"])

    quotas.UserCreate(data["category"], data["group"])

    admin_table_update("users", data)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


# Add user
@app.route("/api/v3/admin/user", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_user_insert(payload):
    try:
        # TODO: Check if user can create in quotas
        # Required

        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )

    p = Password()
    data["password"] = p.encrypt(data["password"])
    data["id"] = None
    data["accessed"] = time.time()

    data = _validate_item("user", data)

    ownsUserId(payload, data["id"])
    itemExists("categories", data["category"])
    itemExists("groups", data["group"])
    quotas.UserCreate(category_id=data["category"], group_id=data["group"])

    admin_table_insert("users", data)

    return (
        json.dumps(data),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/user", methods=["DELETE"])
@has_token
def api_v3_admin_user_delete(payload):

    data = request.get_json()

    for user in data:
        ownsUserId(payload, user["id"])
        users.Delete(user["id"])

    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/templates", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_templates(payload):
    return (
        json.dumps(users.TemplatesAllowed(payload)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/user/<user_id>/templates", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_user_templates(payload, user_id=False):
    if user_id == False:
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

    ownsUserId(payload, user_id)
    templates = users.TemplatesAllowed(user_id)
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

    ownsUserId(payload, user_id)
    return (
        json.dumps(users.Desktops(user_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/user/check", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_user_check(payload):

    data = request.get_json()
    log.error(data)

    desktops = []
    for user in data:
        for desktop in users._user_delete_checks(user["id"]):
            ownsDomainId(payload, desktop["id"])
            desktops.append(desktop)

    return (
        json.dumps(desktops),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/category/<category_id>", methods=["GET"])
@is_admin
def api_v3_admin_category(payload, category_id):
    ownsCategoryId(payload, category_id)
    return (
        json.dumps(users.CategoryGet(category_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/category/<category_id>", methods=["PUT"])
@is_admin
def api_v3_admin_edit_category(payload, category_id):
    ownsCategoryId(payload, category_id)

    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )

    data = _validate_item("category", data)

    admin_table_update("categories", data)
    return json.dumps(data), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/quota", methods=["PUT"])
@is_admin_or_manager
def api_v3_admin_quota(payload):
    quota = request.get_json()

    if "limits" in quota.keys():
        toUpdate = quota["limits"]
        kind = "limits"
    if "quota" in quota.keys():
        toUpdate = quota["quota"]
        kind = "quota"

    ownsCategoryId(payload, quota["id"])

    if "propagate" in quota.keys():
        propagate = quota["propagate"]
    else:
        propagate = False

    try:
        if quota["table"] == "groups" and "limits" in quota.keys():
            group = users.GroupGet(quota["id"])
            category = users.CategoryGet(group["parent_category"], True)

            if category["limits"] != False:
                for k, v in category["limits"].items():
                    if v < quota["limits"][k]:
                        quota["limits"][k] = v
        users.UpdateQuota(quota["id"], toUpdate, quota["table"], kind)

    except:
        raise Error("bad_request")

    if propagate:
        if quota["table"] == "categories":

            for group in users.GroupsGet():
                if group["parent_category"] == quota["id"]:
                    users.UpdateQuota(group["id"], toUpdate, "groups", "quota")

                    for user in users.List():  ## NO FUNCIONA???
                        if user["group"] == group["id"]:
                            users.Update(user["id"], quota=toUpdate)

        if quota["table"] == "groups":
            for user in users.List():
                if user["group"] == quota["id"]:
                    users.Update(user["id"], quota=toUpdate)

    return json.dumps(quota), 200, {"Content-Type": "application/json"}


# Add category
@app.route("/api/v3/admin/category", methods=["POST"])
@is_admin
def api_v3_admin_category_insert(payload):
    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )

    category = _validate_item("category", data)

    ## Create associated Main group
    group = {
        "uid": "Main",
        "description": "[" + category["name"] + "] main group",
        "parent_category": category["id"],
        "name": "Main",
    }

    group = _validate_item("group", group)

    admin_table_insert("categories", category)
    admin_table_insert("groups", group)
    return (
        json.dumps(category),
        200,
        {"Content-Type": "application/json"},
    )


# Add group
@app.route("/api/v3/admin/group", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_group_insert(payload):
    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )

    if payload["role_id"] == "manager":
        data["parent_category"] = payload["category_id"]

    data["description"] = "[" + data["parent_category"] + "] " + data["description"]

    ownsCategoryId(payload, data["parent_category"])

    data = _validate_item("group", data)

    admin_table_insert("groups", data)

    return json.dumps(data), 200, {"Content-Type": "application/json"}


# Enrollment group
@app.route("/api/v3/admin/group/enrollment", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_group_enrollment(payload):

    data = request.get_json()
    ownsCategoryId(payload, users.GroupGet(data["group_id"])["parent_category"])

    code = users.EnrollmentAction(data)

    return json.dumps(code), 200, {"Content-Type": "application/json"}


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
    ownsCategoryId(payload, users.GroupGet(group_id)["parent_category"])
    users.GroupDelete(group_id)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/user/<user_id>/vpn/<kind>/<os>", methods=["GET"])
@app.route("/api/v3/admin/user/<user_id>/vpn/<kind>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_user_vpn(payload, user_id, kind, os=False):
    ownsUserId(payload, user_id)
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
    except:
        raise Error(
            "bad_request",
            "Admin secret invalid body data",
            traceback.format_exc(),
        )

    if role_id == None or domain == None or kid == None or category_id == None:
        raise Error(
            "bad_request",
            "Admin secret missing body data",
            traceback.format_exc(),
        )

    secret = users.Secret(kid, description, role_id, category_id, domain)
    return json.dumps({"secret": secret}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/secret/<kid>", methods=["DELETE"])
@is_admin
def api_v3_admin_secret_delete(payload, kid):
    users.SecretDelete(kid)
    return json.dumps({}), 200, {"Content-Type": "application/json"}
