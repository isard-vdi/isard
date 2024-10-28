#
#   Copyright © 2024 Naomi Hidalgo
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
from isardvdi_common.default_storage_pool import DEFAULT_STORAGE_POOL_ID
from isardvdi_common.storage_pool import StoragePool

from api import app

from ..libv2.api_hypervisors import check_storage_pool_availability
from ..libv2.api_storage import (
    add_storage_pool,
    delete_storage_pool,
    get_storage_pool,
    get_storage_pools,
    update_storage_pool,
)
from ..libv2.validators import _validate_item
from .decorators import has_token, is_admin, is_admin_or_manager


@app.route("/api/v3/admin/storage_pool", methods=["POST"])
@is_admin
def admin_storage_pool_add(payload):
    data = request.get_json()
    data = _validate_item("storage_pool", data)

    add_storage_pool(data)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/storage_pools", methods=["GET"])
@is_admin
def admin_storage_pools_get(payload):
    return (
        json.dumps(get_storage_pools()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/storage_pool/<storage_pool_id>", methods=["GET"])
@is_admin
def admin_storage_pool_get(payload, storage_pool_id):
    storage_pool = get_storage_pool(storage_pool_id)
    storage_pool["is_default"] = storage_pool_id == DEFAULT_STORAGE_POOL_ID
    return (
        json.dumps(storage_pool),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/storage_pool/path/", methods=["PUT"])
@is_admin_or_manager
def admin_storage_pool_get_by_path(payload):
    path = request.get_json()["path"]
    storage_pool = get_storage_pool(StoragePool.get_by_path(path)[0].id)
    storage_pool["is_default"] = storage_pool["id"] == DEFAULT_STORAGE_POOL_ID
    return (
        json.dumps(storage_pool),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/storage_pool/<storage_pool_id>", methods=["PUT"])
@is_admin
def admin_storage_pool_update(payload, storage_pool_id):
    data = request.get_json()
    data = _validate_item("storage_pool_update", data)

    update_storage_pool(storage_pool_id, data)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/storage_pool/<storage_pool_id>", methods=["DELETE"])
@is_admin
def admin_storage_pool_delete(payload, storage_pool_id):
    delete_storage_pool(storage_pool_id)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/storage_pool/availability", methods=["GET"])
@has_token
def admin_storage_pool_check_availability(payload):

    return (
        json.dumps(check_storage_pool_availability(payload["category_id"])),
        200,
        {"Content-Type": "application/json"},
    )
