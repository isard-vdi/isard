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

import json

from flask import request

from api import app

from .._common.api_exceptions import Error
from ..libv2.api_user_storage import (
    isard_user_storage_get_provider,
    isard_user_storage_get_providers,
    isard_user_storage_get_users,
    isard_user_storage_provider_basic_auth_add,
    isard_user_storage_provider_basic_auth_add_intra_docker,
    isard_user_storage_provider_basic_auth_test,
    isard_user_storage_provider_delete,
    isard_user_storage_provider_reset,
    isard_user_storage_reset_all,
    isard_user_storage_sync_groups,
    isard_user_storage_sync_users,
)
from ..libv2.validators import _validate_item
from .decorators import checkDuplicate, is_admin

# Auto create nextcloud instance intra docker if this is an all-in-one installation
isard_user_storage_provider_basic_auth_add_intra_docker()


@app.route("/api/v3/admin/user_storage/conn_test", methods=["POST"])
@is_admin
def admin_user_storage_test(payload):
    data = request.get_json(force=True)
    # TODO: Check cerberus schema
    isard_user_storage_provider_basic_auth_test(
        data["provider"],
        data["url"],
        data["urlprefix"],
        data["user"],
        data["password"],
        data["verify_cert"],
    )
    return json.dumps({})


@app.route("/api/v3/admin/user_storage", methods=["GET"])
@is_admin
def admin_user_storage_list(payload):
    return json.dumps(isard_user_storage_get_providers())


@app.route("/api/v3/admin/user_storage/<provider_id>", methods=["GET"])
@is_admin
def admin_user_storage_get(payload, provider_id):
    return json.dumps(isard_user_storage_get_provider(provider_id))


@app.route("/api/v3/admin/user_storage/<provider_id>", methods=["DELETE"])
@is_admin
def admin_user_storage_remove(payload, provider_id):
    isard_user_storage_provider_delete(provider_id)
    return json.dumps({})


@app.route("/api/v3/admin/user_storage/<provider_id>/reset", methods=["DELETE"])
@is_admin
def admin_user_storage_reset(payload, provider_id):
    isard_user_storage_provider_reset(provider_id)
    return json.dumps({})


@app.route("/api/v3/admin/user_storage/reset/all", methods=["DELETE"])
@is_admin
def admin_user_storage_reset_all(payload):
    isard_user_storage_reset_all()
    return json.dumps({})


@app.route("/api/v3/admin/user_storage/<auth_protocol>", methods=["POST"])
@is_admin
def admin_user_storage_add(payload, auth_protocol):
    data = request.get_json(force=True)
    data = _validate_item("user_storage", data)
    checkDuplicate("user_storage", data["name"])
    if auth_protocol == "auth_basic":
        return json.dumps(
            {
                "id": isard_user_storage_provider_basic_auth_add(
                    data["provider"],
                    data["name"],
                    data["description"],
                    data["url"],
                    data["urlprefix"],
                    data["access"],
                    data["quota"],
                    data["user"],
                    data["password"],
                    data["verify_cert"],
                )
            }
        )
    if auth_protocol == "auth_oauth2":
        raise Error("not_found", "Not implemented")
    raise Error("not_found", "Method not implemented")


@app.route("/api/v3/admin/user_storage/<provider_id>/sync/<item>", methods=["PUT"])
@is_admin
def admin_user_storage_sync(payload, provider_id, item):
    # TODO: Check cerberus schema
    if item in ["groups", "all"]:
        isard_user_storage_sync_groups(provider_id)
    if item in ["users", "all"]:
        isard_user_storage_sync_users(provider_id)
    return json.dumps({})


## TABLE VIEWS


@app.route("/api/v3/admin/user_storage/users", methods=["GET"])
@is_admin
def admin_user_storage_users(payload):
    return json.dumps(isard_user_storage_get_users())
