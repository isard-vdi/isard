# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import time
import traceback

from flask import request

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.api_admin import (
    admin_table_delete,
    admin_table_insert,
    admin_table_list,
    admin_table_update,
)
from ..libv2.api_exceptions import Error
from ..libv2.api_users import ApiUsers, Password
from ..libv2.quotas import Quotas
from ..libv2.validators import _validate_item

quotas = Quotas()
users = ApiUsers()

from ..libv2.isardVpn import isardVpn

vpn = isardVpn()

from .decorators import (
    CategoryNameGroupNameMatch,
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
    if payload["role_id"] == "manager":
        userslist = users.List(payload["category_id"])
    else:
        userslist = users.List()
    return json.dumps(userslist), 200, {"Content-Type": "application/json"}


# Update user
@app.route("/api/v3/admin/user/<user_id>", methods=["PUT"])
@has_token
def api_v3_admin_user_update(payload, user_id):

    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )

    user = users.Get(user_id)

    ownsUserId(payload, user_id)
    ownsCategoryId(payload, user["category"])

    if data.get("secondary_groups"):
        if len(data["secondary_groups"]) > 0:
            users.check_secondary_groups_category(
                data["category"], data["secondary_groups"]
            )

    itemExists("categories", user["category"])
    itemExists("groups", user["group"])

    data["id"] = user_id
    data = _validate_item("user_update", data)

    if "password" in data:
        data["password"] = Password().encrypt(data["password"])

    if "active" in data:
        data["active"] = not data["active"]

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
    data["accessed"] = int(time.time())

    if data["bulk"]:
        match = CategoryNameGroupNameMatch(data["category"], data["group"])
        data["category"] = users.CategoryGetByName(match["category"])["id"]
        data["group"] = users.GroupGetByNameCategory(match["group"], data["category"])[
            "id"
        ]

    data["username"] = data["username"].replace(" ", "")
    if data["provider"] == "local":
        data["uid"] = data["username"]
    data = _validate_item("user", data)

    ownsCategoryId(payload, data["category"])

    if data.get("secondary_groups"):
        if len(data["secondary_groups"]) > 0:
            users.check_secondary_groups_category(
                data["category"], data["secondary_groups"]
            )

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

        if not user.get("username"):
            user = users.Get(user["id"])
        if (
            user["username"] == "admin"
            and users.GroupGet(user["group"])["name"] == "Default"
            and users.CategoryGet(user["category"])["name"] == "Default"
        ):
            raise Error(
                "forbidden", "Can not delete default admin", traceback.format_exc()
            )
    for user in data:
        if not user.get("username"):
            user = users.Get(user["id"])
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


@app.route("/api/v3/admin/users/delete/check", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_users_delete_check(payload):

    data = request.get_json()

    desktops = []
    for user in data:
        for desktop in users._delete_checks(user["id"], "user"):
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


@app.route("/api/v3/admin/quota/group/<group_id>", methods=["PUT"])
@is_admin_or_manager
def api_v3_admin_quotas_category(payload, group_id):
    data = request.get_json()
    propagate = True if "propagate" in data.keys() else False
    if data["quota"]:
        data["id"] = group_id
        _validate_item("group_update", data)
    if data["role"] == "all_roles":
        data["role"] = False
    group = users.GroupGet(group_id)
    ownsCategoryId(payload, group["parent_category"])
    users.UpdateGroupQuota(group, data["quota"], propagate, data["role"])
    return json.dumps(data), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/quota/category/<category_id>", methods=["PUT"])
@is_admin_or_manager
def api_v3_admin_quota_category(payload, category_id):
    data = request.get_json()
    propagate = True if "propagate" in data.keys() else False
    if data["quota"]:
        data["id"] = category_id
        _validate_item("category_update", data)
    if data["role"] == "all_roles":
        data["role"] = False
    ownsCategoryId(payload, category_id)
    users.UpdateCategoryQuota(category_id, data["quota"], propagate, data["role"])
    return json.dumps(data), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/limits/group/<group_id>", methods=["PUT"])
@is_admin_or_manager
def api_v3_admin_limits_group(payload, group_id):
    data = request.get_json()
    if data["limits"]:
        data["id"] = group_id
        _validate_item("group_update", data)
    group = users.GroupGet(group_id)
    ownsCategoryId(payload, group["parent_category"])
    users.UpdateGroupLimits(group, data["limits"])
    return json.dumps(data), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/limits/category/<category_id>", methods=["PUT"])
@is_admin
def api_v3_admin_limits_category(payload, category_id):
    data = request.get_json()
    propagate = True if "propagate" in data.keys() else False
    if data["limits"]:
        data["id"] = category_id
        _validate_item("category_update", data)
    ownsCategoryId(payload, category_id)
    users.UpdateCategoryLimits(category_id, data["limits"], propagate)
    return json.dumps(data), 200, {"Content-Type": "application/json"}


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
    itemExists("categories", data["parent_category"])

    data = _validate_item("group", data)

    admin_table_insert("groups", data)

    return json.dumps(data), 200, {"Content-Type": "application/json"}


# Enrollment group
@app.route("/api/v3/admin/group/enrollment", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_group_enrollment(payload):

    data = request.get_json()
    ownsCategoryId(payload, users.GroupGet(data["id"])["parent_category"])

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


@app.route("/api/v3/admin/delete/check", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_delete_check(payload):

    data = request.get_json()

    desktops = []
    for desktop in users._delete_checks(data["id"], data["table"]):
        ownsDomainId(payload, desktop["id"])
        desktops.append(desktop)

    return (
        json.dumps(desktops),
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
    data = request.get_json()
    data = _validate_item("secrets", data)
    itemExists("categories", data["category_id"])
    itemExists("roles", data["role_id"])

    admin_table_insert("secrets", data)
    return (
        json.dumps({"secret": data["secret"]}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/secret/<kid>", methods=["DELETE"])
@is_admin
def api_v3_admin_secret_delete(payload, kid):
    _validate_item("secrets_delete", {"id": kid})
    admin_table_delete("secrets", kid)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/userschema", methods=["POST"])
@is_admin_or_manager
def admin_userschema(payload):
    dict = {}
    dict["role"] = admin_table_list(
        "roles",
        pluck=["id", "name", "description", "sortorder"],
        order_by="sortorder",
        without=False,
    )
    if payload["role_id"] == "manager":
        dict["role"] = [
            r for r in dict["role"] if r["id"] in ["manager", "advanced", "user"]
        ]
        # dict["category"] = payload["category_id"]

    if payload["role_id"] == "manager":
        dict["category"] = [
            admin_table_list(
                "categories",
                pluck=["id", "name", "description"],
                id=payload["category_id"],
            )
        ]
    else:
        dict["category"] = admin_table_list(
            "categories",
            pluck=["id", "name", "description"],
            order_by="name",
            without=False,
        )

    if payload["role_id"] == "manager":
        dict["group"] = admin_table_list(
            "groups",
            pluck=["id", "name", "description", "parent_category", "linked_groups"],
            order_by="name",
            without=False,
            id=payload["category_id"],
            index="parent_category",
        )
    else:
        dict["group"] = admin_table_list(
            "groups",
            pluck=["id", "name", "description", "parent_category", "linked_groups"],
            order_by="name",
            without=False,
        )
        for g in dict["group"]:
            if "parent_category" in g.keys():
                g["name"] = "[" + g["parent_category"] + "] " + g["name"]
    return json.dumps(dict), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/users/validate", methods=["POST"])
@app.route("/api/v3/admin/users/validate/allow_update", methods=["POST"])
@is_admin_or_manager
def admin_users_validate(payload):
    user_list = request.get_json()
    for i, user in enumerate(user_list):
        _validate_item("user_from_csv", user)

        if payload["role_id"] == "manager":
            if user["role"] not in ["manager", "advanced", "user"]:
                raise Error(
                    "bad_request",
                    "Role " + user["role"] + " not in manager, advanced or user",
                    traceback.format_exc(),
                )
            user["category"] = users.CategoryGetByName(payload["category_id"])["name"]

        else:
            if user["role"] not in ["admin", "manager", "advanced", "user"]:
                raise Error(
                    "bad_request",
                    "Role " + user["role"] + " not in admin, manager, advanced or user",
                    traceback.format_exc(),
                )

        category_id = users.CategoryGetByName(user["category"])["id"]
        cg_data = CategoryNameGroupNameMatch(user["category"], user["group"])
        user_list[i]["category_id"] = cg_data["category_id"]
        user_list[i]["group_id"] = cg_data["group_id"]

        user_id = users.GetByProviderCategoryUID(
            "local", category_id, user["username"].replace(" ", "")
        )

        if len(user_id) > 0:
            if request.path.split("?")[0].endswith("/allow_update"):
                user_list[i]["exists"] = True
            else:
                raise
        else:
            user_list[i]["exists"] = False

    return json.dumps(user_list), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/users/check/by/provider", methods=["POST"])
@is_admin_or_manager
def admin_users_getby_provider_category_uid(payload):
    data = request.get_json()
    category_id = users.CategoryGetByName(data["category"])["id"]

    user_id = users.GetByProviderCategoryUID(
        data["provider"],
        category_id,
        data["uid"].replace(" ", "_"),
    )
    if len(user_id) > 0:
        return json.dumps(user_id[0]["id"]), 200, {"Content-Type": "application/json"}
    else:
        raise Error("not_found", "User not found")
