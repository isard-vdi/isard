#
#   Copyright © 2023 Naomi Hidalgo
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

from ..libv2.api_authentication import (
    add_policy,
    delete_policy,
    edit_policy,
    force_policy_at_login,
    get_disclaimer_template,
    get_policies,
    get_policy,
    get_providers,
)
from ..libv2.validators import _validate_item
from .decorators import is_admin


@app.route("/api/v3/admin/authentication/policy", methods=["POST"])
@is_admin
def admin_authentication_policy_add(payload):
    data = request.get_json()
    data = _validate_item("policy", data)

    add_policy(data)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/authentication/policies/local", methods=["GET"])
@is_admin
def admin_authentication_policies(payload):
    policies = get_policies()

    return (
        json.dumps(policies),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/authentication/policy/<policy_id>", methods=["GET"])
@is_admin
def admin_authentication_policy(payload, policy_id):
    policies = get_policy(policy_id)

    return (
        json.dumps(policies),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/authentication/policy/<policy_id>", methods=["PUT"])
@is_admin
def admin_authentication_policy_edit(payload, policy_id):
    data = request.get_json()
    data = _validate_item("policy_edit", data)

    edit_policy(policy_id, data)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/authentication/policy/<policy_id>", methods=["DELETE"])
@is_admin
def admin_authentication_policy_delete(payload, policy_id):
    delete_policy(policy_id)

    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/authentication/providers", methods=["GET"])
@is_admin
def admin_authentication_providers(payload):
    providers = get_providers()
    return (
        json.dumps(providers),
        200,
        {"Content-Type": "application/json"},
    )


@app.route(
    "/api/v3/admin/authentication/force_validate/email/<policy_id>", methods=["PUT"]
)
@is_admin
def admin_force_email(payload, policy_id):
    force_policy_at_login(policy_id, "email_verified")
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route(
    "/api/v3/admin/authentication/force_validate/disclaimer/<policy_id>",
    methods=["PUT"],
)
@is_admin
def admin_force_disclaimer(payload, policy_id):
    force_policy_at_login(policy_id, "disclaimer_accepted")
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route(
    "/api/v3/admin/authentication/force_validate/password/<policy_id>",
    methods=["PUT"],
)
@is_admin
def admin_force_password(payload, policy_id):
    force_policy_at_login(policy_id, "password_last_updated")
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )
