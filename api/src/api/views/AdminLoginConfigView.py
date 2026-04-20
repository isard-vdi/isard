#
#   Copyright © 2024 Pau Abril Iranzo
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
from urllib.parse import urlparse

from flask import jsonify, request
from isardvdi_common.api_exceptions import Error
from isardvdi_common.category import Category
from isardvdi_common.configuration import Configuration

from api import app

from ..libv2.validators import _validate_item
from .decorators import check_permissions, is_admin
from .PublicView import clear_login_config_cache


def _handle_login_notification_update(category_id=None):
    try:
        data = request.get_json()
    except:
        raise Error("bad_request")

    data = _validate_item("login_notification", data)

    for key in ["cover", "form"]:
        if isinstance(data.get(key), dict):
            button_url = (
                data[key].get("button", {}).get("url")
                if isinstance(data[key].get("button"), dict)
                else None
            )
            if button_url and urlparse(button_url).scheme not in ("http", "https"):
                raise Error("bad_request", "Invalid URL scheme in button URL")

    if category_id:
        current = Category(category_id).login_notification or {}
    else:
        current = Configuration.login or {}

    changed = False
    for position, key in (
        ("cover", "notification_cover"),
        ("form", "notification_form"),
    ):
        position_data = data.get(position)
        if position_data is None:
            continue
        if "enabled" not in position_data:
            position_data["enabled"] = current.get(key, {}).get("enabled", False)
        current[key] = position_data
        changed = True

    if not changed:
        return (json.dumps({}), 200, {"Content-Type": "application/json"})

    # Write the full dict — RethinkBase's ORM cache replaces on write.
    if category_id:
        Category(category_id).login_notification = current
    else:
        Configuration.login = current
    clear_login_config_cache()
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


def _handle_login_notification_enable(notification_type, category_id=None):
    data = request.get_json(force=True)
    enabled = data.get("enabled")

    if enabled is None:
        raise Error("bad_request", "Enabled field is required")

    notification_key = f"notification_{notification_type}"

    if category_id:
        current = Category(category_id).login_notification or {}
    else:
        current = Configuration.login or {}

    current_notif = current.get(notification_key) or {}
    current_notif["enabled"] = enabled
    current[notification_key] = current_notif

    # Write the full dict — RethinkBase's ORM cache replaces on write.
    if category_id:
        Category(category_id).login_notification = current
    else:
        Configuration.login = current
    clear_login_config_cache()
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/login_config/notification", methods=["PUT"])
@is_admin
def api_v3_login_notification_update(payload):
    return _handle_login_notification_update()


@app.route("/api/v3/login_config/notification/cover/enable", methods=["PUT"])
@is_admin
def api_v3_login_notification_cover_enable(payload):
    """

    Allows to enable or disable the login notification for the cover.

    :param payload: JWT payload
    :type payload: dict
    :return: JSON response
    :rtype: Set with Flask response values and data in JSON

    """
    return _handle_login_notification_enable("cover")


@app.route("/api/v3/login_config/notification/form/enable", methods=["PUT"])
@is_admin
def api_v3_login_notification_form_enable(payload):
    """

    Allows to enable or disable the login notification for the form.

    Enabled specification in JSON:
    {
        "enabled": Whether the login notification is enabled or not. (bool)
    }

    :param payload: JWT payload
    :type payload: dict
    :return: JSON response
    :rtype: Set with Flask response values and data in JSON

    """
    return _handle_login_notification_enable("form")


@app.route("/api/v3/admin/category/<category_id>/login_notification", methods=["PUT"])
@check_permissions("login_notification")
def api_v3_category_login_notification_update(payload, category_id):
    return _handle_login_notification_update(category_id)


@app.route(
    "/api/v3/admin/category/<category_id>/login_notification/cover/enable",
    methods=["PUT"],
)
@check_permissions("login_notification")
def api_v3_category_login_notification_cover_enable(payload, category_id):
    return _handle_login_notification_enable("cover", category_id)


@app.route(
    "/api/v3/admin/category/<category_id>/login_notification/form/enable",
    methods=["PUT"],
)
@check_permissions("login_notification")
def api_v3_category_login_notification_form_enable(payload, category_id):
    return _handle_login_notification_enable("form", category_id)
