#
#   Copyright © 2022 Josep Maria Viñolas Auquer
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
import logging as log
import traceback

from flask import request
from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.api_admin import ApiAdmin
from ..libv2.api_storage_physical import (
    phy_storage_delete,
    phy_storage_host,
    phy_storage_list,
    phy_storage_reset_domains,
    phy_storage_reset_media,
    phy_storage_update,
    phy_storage_update_deleted,
    phy_storage_upgrade_to_storage,
)
from .decorators import is_admin, is_admin_or_manager

admins = ApiAdmin()


@app.route("/api/v3/admin/storage/physical/update_deleted/<type>", methods=["GET"])
@is_admin
def api_v3_admin_storage_physical_update_deleted(payload, type):
    if type not in ["disks"]:
        raise Error("bad_request", "Table should be disks")
    data = phy_storage_update_deleted(type)
    return (
        json.dumps(data),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/storage/physical/<table>", methods=["GET"])
@is_admin
def api_v3_admin_get_storage_physical(payload, table):
    if table not in ["domains", "media"]:
        raise Error("bad_request", "Table should be domains or media")
    return (
        json.dumps(phy_storage_list(table)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/storage/physical/<table>", methods=["PUT"])
@is_admin
def api_v3_admin_put_storage_physical(payload, table):
    data = request.get_json()
    # validate item
    phy_storage_update(table, [data])
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/storage/physical/init/<table>", methods=["PUT"])
@is_admin
def api_v3_admin_init_storage_physical(payload, table):
    data = request.get_json()
    # validate item
    if table == "domains":
        phy_storage_reset_domains(data)
    if table == "media":
        phy_storage_reset_media(data)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/storage/physical/<table>/<path_id>", methods=["DELETE"])
@is_admin
def api_v3_admin_delete_storage_physical(payload, table, path_id):
    phy_storage_delete(table, path_id)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route(
    "/api/v3/admin/storage/physical/multiple_actions/<action_id>", methods=["POST"]
)
@is_admin
def api_v3_admin_storage_physical_multiple_actions(payload, action_id):
    data = request.get_json()

    if action_id == "upgrade_to_storage":
        result = phy_storage_upgrade_to_storage(data, payload["user_id"])
    else:
        raise Error("bad_request", "Action does not exist.")
    return (
        json.dumps(result),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/storage/pending/multiple_actions", methods=["POST"])
@is_admin_or_manager
def admin_storage_delete_pending_multiple_actions(payload):
    dict = request.get_json(force=True)
    selected_disks = admins.CheckField(
        "storage", "status", "delete_pending", dict["ids"]
    )
    res = admins.MultipleActions("domains", dict["action"], selected_disks)
    if res is True:
        json_data = json.dumps(
            {
                "title": "Processing",
                "text": "Actions will be processed",
                "type": "success",
            }
        )
        http_code = 200
    else:
        json_data = json.dumps(
            {
                "title": "Error",
                "text": res,
                "type": "error",
            }
        )
        http_code = 409
    return json_data, http_code, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/storage/physical/storage_host", methods=["GET"])
@is_admin
def api_v3_admin_storage_physical_host(payload):
    return (
        json.dumps(phy_storage_host()),
        200,
        {"Content-Type": "application/json"},
    )
