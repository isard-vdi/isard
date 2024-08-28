#
#   Copyright © 2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import html
import json
import logging as log
import time
import traceback

import gevent
from flask import request
from flask_login import logout_user
from isardvdi_common.api_exceptions import Error

from api import app

from .. import socketio
from ..libv2.api_admin import (
    admin_table_delete,
    admin_table_insert,
    admin_table_list,
    admin_table_update,
)
from ..libv2.api_allowed import ApiAllowed
from ..libv2.api_users import (
    ApiUsers,
    Password,
    get_user,
    get_user_full_data,
    user_exists,
)
from ..libv2.quotas import Quotas
from ..libv2.quotas_process import QuotasProcess
from ..libv2.users import *
from ..libv2.validators import _validate_item

quotas = Quotas()
users = ApiUsers()
allowed = ApiAllowed()

from ..libv2.isardVpn import isardVpn

vpn = isardVpn()

from cachetools import TTLCache, cached

from .decorators import (
    CategoryNameGroupNameMatch,
    checkDuplicate,
    checkDuplicateCustomURL,
    checkDuplicateUser,
    has_token,
    is_admin,
    is_admin_or_manager,
    is_auto_register,
    itemExists,
    ownsCategoryId,
    ownsUserId,
)


@app.route("/api/v3/admin/jwt/<user_id>", methods=["GET"])
@has_token
def api_v3_admin_jwt(payload, user_id):
    ownsUserId(payload, user_id)
    logout_user()
    jwt = users.Jwt(user_id)
    return jwt


@app.route("/api/v3/admin/user/<user_id>/exists", methods=["GET"])
@has_token
def api_v3_admin_user_exists(payload, user_id):
    ownsUserId(payload, user_id)
    return (
        json.dumps(user_exists(user_id)),
        200,
        {"Content-Type": "application/json"},
    )


# Define a custom key function
def user_id_key(_, user_id):
    return user_id


@cached(cache=TTLCache(maxsize=100, ttl=60), key=user_id_key)
@app.route("/api/v3/admin/user/<user_id>", methods=["GET"])
@has_token
def api_v3_admin_user(payload, user_id):
    ownsUserId(payload, user_id)
    return (
        json.dumps(get_user_full_data(user_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/user/<user_id>/raw", methods=["GET"])
@has_token
def api_v3_admin_user_raw(payload, user_id):
    ownsUserId(payload, user_id)
    return json.dumps(get_user(user_id)), 200, {"Content-Type": "application/json"}


# Users table list admin panel Management and QuotasLimits
@app.route("/api/v3/admin/users", methods=["GET"])
@app.route("/api/v3/admin/users/<nav>/users", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_users(payload, nav=None):
    category_id = payload["category_id"] if payload["role_id"] == "manager" else None
    userslist = users.list_users(nav, category_id)

    return json.dumps(userslist), 200, {"Content-Type": "application/json"}


# Groups table list admin panel Management and QuotasLimits
@app.route("/api/v3/admin/users/<nav>/groups", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_groups_nav(payload, nav):
    if nav == "management":
        if payload["role_id"] == "manager":
            groupslist = users.list_groups("management", payload["category_id"])
        else:
            groupslist = users.list_groups("management")

    elif nav == "quotas_limits":
        if payload["role_id"] == "manager":
            groupslist = users.list_groups("quotas_limits", payload["category_id"])
        else:
            groupslist = users.list_groups("quotas_limits")

    return json.dumps(groupslist), 200, {"Content-Type": "application/json"}


# Categories table list admin panel Management and QuotasLimits
@app.route("/api/v3/admin/users/<nav>/categories", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_categories_nav(payload, nav):
    if nav == "management":
        if payload["role_id"] == "manager":
            categorieslist = users.list_categories("management", payload["category_id"])
        else:
            categorieslist = users.list_categories("management")

    elif nav == "quotas_limits":
        if payload["role_id"] == "manager":
            categorieslist = users.list_categories(
                "quotas_limits", payload["category_id"]
            )
        else:
            categorieslist = users.list_categories("quotas_limits")

    return json.dumps(categorieslist), 200, {"Content-Type": "application/json"}


# Update user
@app.route("/api/v3/admin/users/csv", methods=["PUT"])
@is_admin_or_manager
def api_v3_admin_user_csv(payload):
    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )
    for user_data in data["users"]:
        user_data = _validate_item("user_from_csv_edit", user_data)
        ownsUserId(payload, user_data["id"])

        if user_data.get("password"):
            user_data["password_last_updated"] = (
                0  # password must be restored by user after an admin changes it
            )

        users.Update([user_data["id"]], user_data)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/user/<user_id>", methods=["PUT"])
@app.route("/api/v3/admin/users/bulk", methods=["PUT"])
@is_admin_or_manager
def api_v3_admin_user_update(payload, user_id=None):
    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )

    if user_id:
        data["ids"] = [user_id]

    for user_id in data["ids"]:
        if user_id == payload["user_id"] and data.get("active") is not None:
            raise Error("forbidden", "Can not deactivate your own account")

        user = users.Get(user_id)
        if (
            user["username"] == "admin"
            and users.GroupGet(user["group"])["name"] == "Default"
            and users.CategoryGet(user["category"])["name"] == "Default"
            and data.get("active") is not None
        ):
            raise Error("forbidden", "Can not deactivate default admin")

        ownsUserId(payload, user_id)
        ownsCategoryId(payload, user["category"])

        if data.get("secondary_groups") is not None:
            if len(data["secondary_groups"]) > 0:
                users.check_secondary_groups_category(
                    user["category"], data["secondary_groups"]
                )

        ## bulk update by creation csv
        if data.get("bulk"):
            match = CategoryNameGroupNameMatch(data["category"], data["group"])
            data["category"] = users.CategoryGetByName(match["category"])["id"]
            data["group"] = users.GroupGetByNameCategory(
                match["group"], data["category"]
            )["id"]

    if "quota" in data:
        data = _validate_item("user_update_quota", data)
        if payload["role_id"] != "admin":
            category_quota = quotas.GetCategoryQuota(payload["category_id"])["quota"]
            if category_quota != False:
                for k, v in category_quota.items():
                    if (
                        data.get("quota")
                        and data.get("quota").get(k)
                        and v < data.get("quota")[k]
                    ):
                        raise Error(
                            "precondition_required",
                            "Can't update "
                            + user["name"]
                            + " "
                            + k
                            + " quota value with a higher value than its category quota,  "
                            + k
                            + " must be equal or lower than "
                            + str(v),
                            traceback.format_exc(),
                        )

    else:
        data = _validate_item("user_update", data)

    if data.get("password") and user_id != payload["user_id"]:
        data["password_last_updated"] = (
            0  # password must be restored by user after an admin changes it
        )

    users.Update(data["ids"], data)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/user/secondary-groups/add", methods=["PUT"])
@is_admin_or_manager
def api_v3_update_secondary_groups_add(payload):
    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )
    for user in data["ids"]:
        ownsUserId(payload, user)
    for group in data["secondary_groups"]:
        ownsCategoryId(payload, users.GroupGet(group)["parent_category"])
    users.UpdateSecondaryGroups("add", data)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/user/secondary-groups/overwrite", methods=["PUT"])
@is_admin_or_manager
def api_v3_update_secondary_groups_overwrite(payload):
    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )
    for user in data["ids"]:
        ownsUserId(payload, user)
    for group in data["secondary_groups"]:
        ownsCategoryId(payload, users.GroupGet(group)["parent_category"])
    users.UpdateSecondaryGroups("overwrite", data)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/user/secondary-groups/delete", methods=["PUT"])
@is_admin_or_manager
def api_v3_update_secondary_groups_delete(payload):
    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )
    for user in data["ids"]:
        ownsUserId(payload, user)
    for group in data["secondary_groups"]:
        ownsCategoryId(payload, users.GroupGet(group)["parent_category"])
    users.UpdateSecondaryGroups("delete", data)
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

    data["id"] = None
    data["accessed"] = int(time.time())
    data["quota"] = False

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
    checkDuplicateUser(data["uid"], data["category"], data["provider"])

    ownsCategoryId(payload, data["category"])

    if data.get("secondary_groups"):
        if len(data["secondary_groups"]) > 0:
            users.check_secondary_groups_category(
                data["category"], data["secondary_groups"]
            )

    itemExists("categories", data["category"])
    itemExists("groups", data["group"])
    if users.GroupGet(data["group"])["parent_category"] != data["category"]:
        raise Error(
            "bad_request",
            "Group "
            + data["group"]
            + " does not belong to category "
            + data["category"],
        )

    quotas.UserCreate(category_id=data["category"], group_id=data["group"])

    p = Password()
    policy = users.get_user_password_policy(data["category"], data["role"])
    p.check_policy(data["password"], policy, username=data["username"])
    data["password"] = p.encrypt(data["password"])

    data["password_history"] = [data["password"]]
    data["password_last_updated"] = int(time.time())
    data["email_verification_token"] = None
    data["email_verified"] = None
    admin_table_insert("users", data)

    return (
        json.dumps(data),
        200,
        {"Content-Type": "application/json"},
    )


# Add user
@app.route("/api/v3/admin/bulk/user", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_create_users_bulk(payload):
    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )

    gevent.spawn(users.generate_users, payload, data)

    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/user", methods=["DELETE"])
@has_token
def api_v3_admin_user_delete(payload):
    data = request.get_json()

    for user in data["user"]:
        ownsUserId(payload, user)

        user = users.Get(user)
        if (
            user["username"] == "admin"
            and user["group"] == "default-default"
            and user["category"] == "default"
        ):
            raise Error(
                "forbidden", "Can not delete default admin", traceback.format_exc()
            )
        elif user["id"] == payload["user_id"]:
            raise Error(
                "forbidden", "Can not delete your own user", traceback.format_exc()
            )
    for user in data["user"]:
        users.Delete(user, payload["user_id"], data["delete_user"])
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


@app.route("/api/v3/admin/category/<category_id>", methods=["GET"])
@is_admin
def api_v3_admin_category(payload, category_id):
    ownsCategoryId(payload, category_id)
    return (
        json.dumps(users.CategoryGet(category_id, True)),
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

    data = _validate_item("category_update", data)
    checkDuplicate("categories", data["name"], item_id=data["id"])
    checkDuplicateCustomURL(data["custom_url_name"], category_id=data["id"])
    admin_table_update("categories", data)
    return json.dumps(data), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/quota/group/<group_id>", methods=["PUT"])
@is_admin_or_manager
def api_v3_admin_quota_group(payload, group_id):
    data = request.get_json()
    propagate = True if "propagate" in data.keys() else False
    if data["quota"]:
        data["id"] = group_id
        data = _validate_item("group_update_quota", data)
    if data["role"] == "all_roles":
        data["role"] = False
    group = users.GroupGet(group_id)
    ownsCategoryId(payload, group["parent_category"])
    users.UpdateGroupQuota(
        group, data["quota"], propagate, data["role"], payload["role_id"]
    )
    return json.dumps(data), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/quota/category/<category_id>", methods=["PUT"])
@is_admin
def api_v3_admin_quota_category(payload, category_id):
    data = request.get_json()
    propagate = True if "propagate" in data.keys() else False
    if data.get("quota"):
        data["id"] = category_id
        data = _validate_item("category_update_quota", data)
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
        data = _validate_item("group_update_quota", data)
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
        _validate_item("category_update_quota", data)
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

    checkDuplicate("categories", category["name"])
    checkDuplicateCustomURL(category["custom_url_name"])

    admin_table_insert("categories", category)
    admin_table_insert("groups", group)
    return (
        json.dumps(category),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/group/<group_id>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_group_get(payload, group_id):
    return (
        json.dumps(users.group_get_full_data(group_id)),
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

    category_name = users.CategoryGet(data["parent_category"])["name"]
    data["description"] = "[" + category_name + "] " + data["description"]

    ownsCategoryId(payload, data["parent_category"])
    itemExists("categories", data["parent_category"])

    data = _validate_item("group", data)
    checkDuplicate("groups", data["name"], category=data["parent_category"])

    admin_table_insert("groups", data)

    return json.dumps(data), 200, {"Content-Type": "application/json"}


# Update group
@app.route("/api/v3/admin/group/<group_id>", methods=["PUT"])
@has_token
def api_v3_admin_group_update(payload, group_id):
    try:
        data = request.get_json()
    except:
        raise Error(
            "bad_request",
            "Unable to parse body data.",
            traceback.format_exc(),
        )
    category = users.GroupGet(group_id)["parent_category"]

    ownsCategoryId(payload, category)
    data = _validate_item("group_update", data)
    checkDuplicate("groups", data["name"], category, item_id=data["id"])

    admin_table_update("groups", data, payload)
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
        json.dumps(users.CategoryDelete(category_id, payload["user_id"])),
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
    if payload["group_id"] == group_id:
        raise Error(
            "precondition_required",
            "Can't delete your own group " + group_id,
            traceback.format_exc(),
        )

    ownsCategoryId(payload, users.GroupGet(group_id)["parent_category"])
    users.GroupDelete(group_id, payload["user_id"])
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/user/delete/check", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_user_delete_check(payload):
    data = request.get_json()
    for user in data["ids"]:
        ownsUserId(payload, user)

    return (
        json.dumps(users._delete_checks(data["ids"], "user")),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/group/delete/check", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_groups_delete_check(payload):
    data = request.get_json()
    for user in data["ids"]:
        ownsCategoryId(payload, users.GroupGet(user)["parent_category"])

    return (
        json.dumps(users._delete_checks(data["ids"], "group")),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/category/delete/check", methods=["POST"])
@is_admin_or_manager
def api_v3_admin_categories_delete_check(payload):
    data = request.get_json()
    for user in data["ids"]:
        ownsCategoryId(payload, user)

    return (
        json.dumps(users._delete_checks(data["ids"], "category")),
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


@app.route("/api/v3/admin/userschema", methods=["GET"])
@is_admin_or_manager
def admin_userschema(payload):
    dict = {}
    dict["role"] = admin_table_list(
        "roles",
        pluck=["id", "name", "description", "sortorder"],
        order_by="sortorder",
        without=False,
    )
    if payload["role_id"] == "admin":
        dict["category"] = admin_table_list(
            "categories",
            pluck=["id", "name", "description"],
            order_by="name",
            without=False,
            merge=False,
        )

        dict["group"] = admin_table_list(
            "groups",
            pluck=["id", "name", "description", "parent_category", "linked_groups"],
            order_by="name",
            without=False,
            merge=False,
        )

    elif payload["role_id"] == "manager":
        dict["role"] = [
            r for r in dict["role"] if r["id"] in ["manager", "advanced", "user"]
        ]
        dict["category"] = [
            admin_table_list(
                "categories",
                pluck=["id", "name", "description", "parent_category", "linked_groups"],
                without=False,
                id=payload["category_id"],
                merge=False,
            )
        ]
        dict["group"] = admin_table_list(
            "groups",
            pluck=["id", "name", "description", "parent_category", "linked_groups"],
            order_by="name",
            without=False,
            id=payload["category_id"],
            index="parent_category",
            merge=False,
        )

    return json.dumps(dict), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/users/csv/validate", methods=["POST"])
@is_admin_or_manager
def admin_users_validate(payload):
    user_list = request.get_json()

    processed_list = []
    errors = []

    for user in user_list:
        # Validate each user
        user = {field: html.escape(str(value)) for field, value in user.items()}
        user = _validate_item("user_from_csv", user)

        try:
            user = users.bulk_user_check(payload, user, "csv")
        except Error as e:
            errors.append(
                f"Skipping user {user['username']}: {e.error.get('description')}"
            )
            continue

        processed_list.append(user)

    return (
        json.dumps({"errors": errors, "users": processed_list}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/users/csv/validate", methods=["PUT"])
@is_admin_or_manager
def admin_users_validate_edit(payload):
    user_list = request.get_json()
    for i, user in enumerate(user_list):
        user = _validate_item("user_from_csv_edit", user)

        cg_data = CategoryNameGroupNameMatch(user["category"], user["group"])
        if user.get("secondary_groups"):
            secondary_groups = []
            for sg_name in user["secondary_groups"]:
                sg = users.GroupGetByNameCategory(sg_name, cg_data["category_id"])
                secondary_groups.append(sg["id"])
            user_list[i]["secondary_groups"] = secondary_groups
            user_list[i]["secondary_groups_names"] = user["secondary_groups"]
        if user.get("name"):
            user_list[i]["name"] = user_list[i]["name"].strip('"')
        try:
            user_list[i]["id"] = users.GetByProviderCategoryUID(
                user["provider"], cg_data["category_id"], user["uid"]
            )[0]["id"]
            ownsUserId(payload, user_list[i]["id"])
        except:
            raise Error(
                "not_found", "User with username " + user["name"] + " not found"
            )

        if user.get("password"):
            p = Password()
            policy = users.get_user_password_policy(user_id=user_list[i]["id"])
            p.check_policy(
                user["password"], policy, user_list[i]["id"], user.get("username")
            )

        user_list[i]["category_id"] = cg_data["category_id"]
        user_list[i]["group_id"] = cg_data["group_id"]

    return json.dumps(user_list), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/check/group/category", methods=["POST"])
@is_admin_or_manager
def check_group_category(payload):
    data = request.get_json()
    enabled = []

    users.check_group_category(data)

    return (
        json.dumps(enabled),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/category/get/<category_name>", methods=["GET"])
@is_admin_or_manager
def admin_users_getby_name(payload, category_name):
    category_id = users.CategoryGetByName(category_name)["id"]

    if len(category_id) > 0:
        return json.dumps(category_id), 200, {"Content-Type": "application/json"}
    else:
        raise Error("not_found", "Category not found")


@app.route("/api/v3/admin/group/get/<category_name>/<group_name>", methods=["GET"])
@is_admin_or_manager
def admin_users_getby_category_and_name(payload, category_name, group_name):
    group_id = users.GroupGetByNameCategory(group_name, category_name)["id"]

    if len(group_id) > 0:
        return json.dumps(group_id), 200, {"Content-Type": "application/json"}
    else:
        raise Error("not_found", "Group not found")


@app.route("/api/v3/admin/socketio/broadcast", methods=["POST"])
@is_admin
def socketio_broadcast(payload):
    data = request.get_json()
    socketio.emit(
        "msg",
        json.dumps({"type": data["type"], "msg": data["message"]}),
        namespace="/administrators",
        broadcast=True,
        include_self=True,
    )
    socketio.emit(
        "msg_" + data["type"],
        json.dumps({"type": data["type"], "msg": data["message"]}),
        namespace="/userspace",
        broadcast=True,
        include_self=True,
    )


@app.route("/api/v3/admin/quotas", methods=["GET"])
@is_admin_or_manager
def admin_quotas(payload):
    return (
        json.dumps(
            QuotasProcess().get(
                user_id=payload.get("user_id"),
                category_id=payload.get("category_id"),
                role_id=payload.get("role_id"),
            )
        ),
        200,
        {"Content-Type": "application/json"},
    )


@cached(TTLCache(maxsize=10, ttl=60))
@app.route("/api/v3/admin/users/search", methods=["POST"])
@is_admin_or_manager
def search_users_for_template(payload):
    term = request.get_json()["term"]
    if payload["role_id"] == "admin":
        result = allowed.get_table_term(
            "users",
            "name",
            term,
            pluck=["id", "name", "uid"],
            query_filter=lambda user: user["role"] != "user",
        )
    else:
        result = allowed.get_table_term(
            "users",
            "name",
            term,
            pluck=["id", "name", "category", "uid"],
            index_key="category",
            index_value=payload["category_id"],
            query_filter=lambda user: user["role"] != "user",
        )

    return json.dumps(result), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/roles", methods=["GET"])
@is_admin_or_manager
def admin_roles(payload):
    users.RoleGet(payload["role_id"])
    return (
        json.dumps(users.RoleGet(payload["role_id"])),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/role/<role_id>", methods=["GET"])
@is_admin
def admin_role(payload, role_id):
    roles = users.RoleGet(payload["role_id"])
    for role in roles:
        if role["id"] == role_id:
            return (
                json.dumps(role),
                200,
                {"Content-Type": "application/json"},
            )
    raise Error("not_found", "Role not found")


@app.route("/api/v3/admin/role/<role_id>", methods=["PUT"])
@is_admin
def admin_role_update(payload, role_id):
    data = request.get_json()
    data = _validate_item("role_update", data)
    admin_table_update("roles", data)
    return json.dumps(data), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/secrets", methods=["GET"])
@is_admin
def admin_secrets(payload):
    return (
        json.dumps(users.Secrets()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/user/required/password-reset/<user_id>", methods=["GET"])
@is_admin
def user_required_password_reset(payload, user_id):
    return (
        json.dumps({"required": users.check_password_expiration(user_id)}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/user/password-policy/<user_id>", methods=["GET"])
@is_admin_or_manager
def admin_user_password_policy(payload, user_id):
    ownsUserId(payload, user_id)
    return (
        json.dumps(users.get_user_password_policy(user_id=user_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route(
    "/api/v3/admin/user/required/disclaimer-acknowledgement/<user_id>", methods=["GET"]
)
@is_admin
def user_required_disclaimer_acknowledgement(payload, user_id):
    return (
        json.dumps({"required": users.check_acknowledged_disclaimer(user_id)}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/user/required/email-verification/<user_id>", methods=["GET"])
@is_admin
def user_required_email_verification(payload, user_id):
    return (
        json.dumps({"required": users.check_verified_email(user_id) == None}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/user/reset-password", methods=["PUT"])
@is_admin
def admin_use_password_update(payload):
    data = request.get_json(force=True)

    if not data.get("password") or not data.get("user_id"):
        raise Error(
            "bad_request",
            "Password and user_id are required",
        )
    user_id = data["user_id"]
    data = _validate_item("user_password_update", data)

    users.change_password(
        data["password"],
        user_id,
    )
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/user/email-category/<email>/<category>", methods=["GET"])
@is_admin
def admin_user_by_email_and_category(payload, email, category):
    return (
        json.dumps({"id": users.get_user_by_email_and_category(email, category)}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/user/appliedquota/<user_id>", methods=["GET"])
@is_admin_or_manager
def admin_get_user_applied_quota(payload, user_id):
    applied_quota = quotas.get_applied_quota(user_id)

    return json.dumps(applied_quota), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/user/auto-register", methods=["POST"])
@is_admin
@is_auto_register
def admin_user_auto_register(payload):
    data = request.get_json()
    data = _validate_item("user_auto_register", data)

    checkDuplicateUser(payload["user_id"], payload["category_id"], payload["provider"])
    user_id = users.Create(
        payload["provider"],
        payload["category_id"],
        payload["user_id"],
        payload["username"],
        payload["name"],
        data["role_id"],
        data["group_id"],
        photo=payload["photo"],
        email=payload["email"],
    )

    return json.dumps({"id": user_id}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/user/reset-vpn/<user_id>", methods=["PUT"])
@is_admin_or_manager
def admin_user_reset_vpn(payload, user_id):
    users.reset_vpn(user_id)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )
