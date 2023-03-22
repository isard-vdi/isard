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

from flask import request

from api import app

from .._common.api_exceptions import Error
from ..libv2.api_storage import Storage

# from ..libv2.api_storage_file import StorageFile
from .decorators import is_admin

api_storage = Storage()


@app.route("/storage/api/storage/disk/info", methods=["POST"])
@is_admin
def storage_disk_info(payload):
    data = request.get_json(force=True)
    return (
        json.dumps(api_storage.get_file_info(data["path_id"])),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/storage/api/storage/disks", methods=["PUT"])
@is_admin
def storage_disk_update(payload):
    return (
        json.dumps(api_storage.update_disks()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/storage/api/storage/media", methods=["PUT"])
@is_admin
def storage_media_update(payload):
    return (
        json.dumps(api_storage.update_media()),
        200,
        {"Content-Type": "application/json"},
    )


# @app.route("/storage/api/storage/disks", methods=["GET"])
# @is_admin
# def storage_list(payload=None):
#     return (
#         json.dumps(api_storage.get_disks()),
#         200,
#         {"Content-Type": "application/json"},
# )


# @app.route("/storage/api/file/<item>/<uuid>", methods=["GET"])
# # @has_token
# def file_info(item, uuid):
#     if item == "size":
#         return (
#             json.dumps(StorageFile(uuid).size()),
#             200,
#             {"Content-Type": "application/json"},
#         )
#     if item == "chain":
#         return (
#             json.dumps(StorageFile(uuid).chain()),
#             200,
#             {"Content-Type": "application/json"},
#         )
#     if item == "disks":
#         return (
#             json.dumps(StorageFile(uuid).disks()),
#             200,
#             {"Content-Type": "application/json"},
#         )


# @app.route("/storage/api/file", methods=["POST"])
# @app.route("/storage/api/file/<from_backing>", methods=["POST"])
# @has_token
# def file_new(payload, from_backing=None):
#     data = request.get_json(force=True)
#     if from_backing == "from_backing":
#         data = _validate_item("new_file_from_backing", data)
#         uuid = StorageFile(uuid).create(
#             data.get("format", "qcow2"), data["backing_file"]
#         )
#     else:
#         data = _validate_item("new_file", data)
#         uuid = StorageFile(uuid).create(data.get("format", "qcow2"), data["size"])
#     return json.dumps(uuid), 200, {"Content-Type": "application/json"}
