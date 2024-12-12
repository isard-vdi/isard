#
#   Copyright © 2023 Miriam Melina Gamboa Valdez
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

import json

import gevent
from flask import request
from isardvdi_common.api_exceptions import Error
from isardvdi_common.tokens import get_jwt_payload, get_user_migration_payload

from api import app

from ..libv2.api_admin import get_user_migration_config, update_user_migration_config
from ..libv2.api_auth import generate_migrate_user_token
from ..libv2.api_authentication import get_provider_config
from ..libv2.api_users import ApiUsers
from ..libv2.validators import _validate_item
from .decorators import has_migration_required_or_login_token, has_token, is_admin

users = ApiUsers()


@app.route("/api/v3/admin/config/user_migration", methods=["GET"])
@is_admin
def api_v3_admin_config_migration(payload):
    """

    Endpoint to retrieve the migration configuration

    :param payload: The payload of the request
    :type payload: dict
    :return: The quota check status
    :rtype: Set with Flask response values and data in JSON

    """
    return (
        json.dumps(get_user_migration_config()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/config/user_migration", methods=["PUT"])
@is_admin
def api_v3_admin_config_migration_update(payload):
    """

    Endpoint to update the migration configuration

    :param payload: The payload of the request
    :type payload: dict
    :return: The quota check status
    :rtype: Set with Flask response values and data in JSON

    """
    if not request.is_json:
        raise Error(
            description="No JSON in body request with user_migration configuration specifications",
        )
    request_json = request.get_json()
    data = _validate_item("user_migration_update", request_json)
    return (
        json.dumps(update_user_migration_config(data)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/user_migration/export", methods=["POST"])
@has_migration_required_or_login_token
def api_v3_user_migration_export(payload):
    """

    Endpoint to start the user migration process

    :param payload: Data from JWT token
    :type payload: dict
    :return: The user migration process status
    :rtype: Set with Flask response values and data in JSON

    """
    resources = users._delete_checks([payload["user_id"]], "user")
    if not any(
        [
            resources["desktops"],
            resources["templates"],
            resources["media"],
            resources["deployments"],
        ]
    ):
        raise Error(
            "bad_request",
            description="No items available for migration",
            description_code="migration_no_items_available",
        )

    token = generate_migrate_user_token(payload["user_id"])["token"]
    token_data = get_jwt_payload(token)
    users.register_migration(token, token_data["user_id"])
    return (
        json.dumps({"token": token}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/user_migration/import", methods=["POST"])
@has_token
def api_v3_user_migration_import(payload):
    """

    Endpoint to continue the user migration process to a target user

    :param payload: Data from JWT token
    :type payload: dict

    """
    if not request.is_json:
        raise Error(
            "bad_request",
            description="No JSON in body request with user_migration configuration specifications",
        )
    request_json = request.get_json()
    data = _validate_item("user_migration_import", request_json)
    errors = users.check_user_migration(data["token"], payload["user_id"])
    if errors:
        return (
            json.dumps(errors[0]),
            428,
            {"Content-Type": "application/json"},
        )

    try:
        get_user_migration_payload(data["token"])
    # If the token is expired delete the migration
    except Error as e:
        if e.error.get("description_code") == "token_expired":
            users.delete_user_migration(data["token"])
        raise e

    # Check if the user has other migrations as imported and reset them
    users.reset_imported_user_migration_by_target_user(payload["user_id"])

    users.update_user_migration(
        data["token"], "imported", target_user_id=payload["user_id"]
    )

    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/user_migration/items", methods=["GET"])
@has_token
def api_v3_user_migration_list(payload):
    """

    Endpoint to retrieve the items in the user migration process

    :param payload: Data from JWT token
    :type payload: dict
    :return: The list of items in the user migration process
    :rtype: Set with Flask response values and data in JSON

    """
    try:
        user_migration = users.get_user_migration_by_target_user(payload["user_id"])
    except Error as e:
        if e.error.get("description_code") == "migration_not_found":
            errors = [
                {
                    "description": "The user migration process was not found.",
                    "description_code": "invalid_token",
                }
            ]
        elif e.error.get("description_code") == "multiple_migrations_found_target_user":
            errors = [
                {
                    "description": "Multiple user migration processes found for the target user.",
                    "description_code": "multiple_migrations_found_target_user",
                }
            ]
        return (
            json.dumps({"errors": errors}),
            428,
            {"Content-Type": "application/json"},
        )
    errors = []

    try:
        get_user_migration_payload(user_migration["token"])
    # If the token is expired delete the migration
    except Error as e:
        if e.error.get("description_code") == "token_expired":
            users.delete_user_migration(user_migration["token"])
        raise e

    errors += users.check_valid_migration(
        user_migration["origin_user"], payload["user_id"], check_quotas=True
    )

    quota_errors = []
    non_quota_errors = []
    if get_user_migration_config()["check_quotas"]:
        non_quota_errors = errors
    else:
        for error in errors:
            if error["description_code"] in [
                "migration_desktop_quota_error",
                "migration_template_quota_error",
                "migration_media_quota_error",
                "migration_deployments_quota_error",
            ]:
                quota_errors.append(error)
            else:
                non_quota_errors.append(error)

    if non_quota_errors:
        return (
            json.dumps({"errors": non_quota_errors}),
            428,
            {"Content-Type": "application/json"},
        )

    items = users._delete_checks([user_migration["origin_user"]], "user")
    items["desktops"] = [
        item
        for item in items["desktops"]
        if item["user"] == user_migration["origin_user"]
    ]
    items["templates"] = [
        item
        for item in items["templates"]
        if item["user"] == user_migration["origin_user"]
    ]
    if quota_errors:
        items["quota_errors"] = quota_errors

    items["origin_user_delete"] = (
        get_provider_config(items["users"][0]["provider"])
        .get("migration", {})
        .get("action_after_migrate", "")
        != "none"
    )

    if (
        not items["desktops"]
        and not items["templates"]
        and not items["media"]
        and not items["deployments"]
    ):
        return (
            json.dumps(
                {
                    "errors": [
                        {
                            "description": "No items to migrate.",
                            "description_code": "no_items_to_migrate",
                        }
                    ]
                }
            ),
            428,
            {"Content-Type": "application/json"},
        )

    return (
        json.dumps(items),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/user_migration/auto", methods=["POST"])
@has_token
def api_v3_user_migration_auto(payload):
    """

    Endpoint to migrate the user items automatically

    :param payload: Data from JWT token
    :type payload: dict
    :return: The user migration process status
    :rtype: Set with Flask response values and data in JSON

    """
    user_migration = users.get_user_migration_by_target_user(payload["user_id"])
    errors = []
    try:
        get_user_migration_payload(user_migration["token"])
    # If the token is expired delete the migration
    except Error as e:
        if e.error.get("description_code") == "token_expired":
            users.delete_user_migration(user_migration["token"])
        raise e

    errors += users.check_valid_migration(
        user_migration["origin_user"], payload["user_id"]
    )

    if errors:
        return (
            json.dumps({"errors": errors}),
            428,
            {"Content-Type": "application/json"},
        )

    # TODO: move to a thread once ws are implemented in frontend

    # gevent.spawn(
    #     users.process_automigrate_user,
    #     user_migration["origin_user"],
    #     payload["user_id"],
    #     user_migration["token"],
    # )
    # return (
    #     json.dumps({}),
    #     200,
    #     {"Content-Type": "application/json"},
    # )

    return (
        json.dumps(
            users.process_automigrate_user(
                user_migration["origin_user"],
                payload["user_id"],
                user_migration["token"],
            )
        ),
        200,
        {"Content-Type": "application/json"},
    )
