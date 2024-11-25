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

from flask import jsonify, request
from isardvdi_common.api_exceptions import Error

from api import app, socketio

from ..libv2.api_admin import get_user_migration_config, update_user_migration_config
from ..libv2.validators import _validate_item
from .decorators import is_admin


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
