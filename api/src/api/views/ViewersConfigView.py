#
#   Copyright © 2024 Miriam Melina Gamboa Valdez
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

from ..libv2.api_viewers_config import (
    get_viewers_config,
    reset_viewers_config,
    update_viewers_config,
)
from .decorators import is_admin


@app.route("/api/v3/admin/viewers-config", methods=["GET"])
@is_admin
def api_v3_viewers_config(payload):
    """
    Returns all the viewers configurations.

    :param payload: Data from JWT
    :type payload: dict
    :return: Array of the viewers configuration
    :rtype: Set with Flask response values and data in JSON
    """
    return (
        json.dumps(get_viewers_config()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/viewers-config/<viewer>", methods=["PUT"])
@is_admin
def api_v3_viewers_config_update(payload, viewer):
    """
    Update a viewer custom configuration.

    Viewer specifications in JSON:
    {
        "custom": "category of the user"
    }
    :param payload: Data from JWT
    :type payload: dict
    :param viewer: Viewer key to be updated
    :type viewer: string
    :return: Array of the viewers configuration
    :rtype: Set with Flask response values and data in JSON
    """
    data = request.get_json(force=True)
    update_viewers_config(viewer, data.get("custom"))
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/viewers-config/reset/<viewer>", methods=["PUT"])
@is_admin
def api_v3_viewers_config_reset(payload, viewer):
    """
    Reset a viewer custom configuration to its default.

    :param payload: Data from JWT
    :type payload: dict
    :param viewer: Viewer key to be updated
    :type viewer: string
    :return: Array of the viewers configuration
    :rtype: Set with Flask response values and data in JSON
    """
    if viewer not in ["file_rdpgw", "file_rdpvpn", "file_spice"]:
        raise Error(
            "bad_request",
            "Invalid viewer value to reset",
        )
    reset_viewers_config(viewer)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )
