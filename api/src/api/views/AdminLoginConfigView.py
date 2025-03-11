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

from flask import request
from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.login import enable_login_notification, update_login_notification
from ..libv2.validators import _validate_item
from .decorators import is_admin


@app.route("/api/v3/login_config/notification", methods=["PUT"])
@is_admin
def api_v3_login_notification_update(payload):
    try:
        data = request.get_json()
    except:
        raise Error("bad_request")

    data = _validate_item("login_notification", data)

    update_login_notification(data)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


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
    data = request.get_json(force=True)
    enabled = data.get("enabled")

    if enabled is None:
        raise Error("bad_request", "Enabled field is required")

    enable_login_notification("cover", enabled)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


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
    data = request.get_json(force=True)
    enabled = data.get("enabled")

    if enabled is None:
        raise Error("bad_request", "Enabled field is required")

    enable_login_notification("form", enabled)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )
