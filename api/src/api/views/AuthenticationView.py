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
    add_email_policy,
    add_password_policy,
    delete_email_policy,
    delete_password_policy,
    edit_email_policy,
    edit_password_policy,
    get_email_policies,
    get_email_policy,
    get_password_policies,
    get_password_policy,
    get_providers,
)
from ..libv2.validators import _validate_item
from .decorators import is_admin

### PASSWORD POLICY


@app.route("/api/v3/admin/authentication/policy/password", methods=["POST"])
@is_admin
def admin_authentication_password_policy_add(payload):
    data = request.get_json()
    data = _validate_item("password_policy", data)

    add_password_policy(data)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/authentication/policies/local/password/", methods=["GET"])
@is_admin
def admin_authentication_password_policies(payload):
    policies = get_password_policies()

    return (
        json.dumps(policies),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/authentication/policy/password/<policy_id>", methods=["GET"])
@is_admin
def admin_authentication_password_policy(payload, policy_id):
    policies = get_password_policy(policy_id)

    return (
        json.dumps(policies),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/authentication/policy/password/<policy_id>", methods=["PUT"])
@is_admin
def admin_authentication_password_policy_edit(payload, policy_id):
    data = request.get_json()
    data = _validate_item("password_policy_edit", data)

    edit_password_policy(policy_id, data)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route(
    "/api/v3/admin/authentication/policy/password/<policy_id>", methods=["DELETE"]
)
@is_admin
def admin_authentication_password_policy_delete(payload, policy_id):
    delete_password_policy(policy_id)

    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


### EMAIL VERIFICATION POLICY


@app.route("/api/v3/admin/authentication/policy/email", methods=["POST"])
@is_admin
def admin_authentication_email_add(payload):
    data = request.get_json()
    data = _validate_item("email_verification", data)

    add_email_policy(data)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/authentication/policies/local/email/", methods=["GET"])
@is_admin
def admin_authentication_email_policies(payload):
    policies = get_email_policies()

    return (
        json.dumps(policies),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/authentication/policy/email/<policy_id>", methods=["GET"])
@is_admin
def admin_authentication_email(payload, policy_id):
    policies = get_email_policy(policy_id)

    return (
        json.dumps(policies),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/authentication/policy/email/<policy_id>", methods=["PUT"])
@is_admin
def admin_authentication_email_edit(payload, policy_id):
    data = request.get_json()
    data = _validate_item("email_verification_edit", data)

    edit_email_policy(policy_id, data)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/authentication/policy/email/<policy_id>", methods=["DELETE"])
@is_admin
def admin_authentication_email_delete(payload, policy_id):
    delete_email_policy(policy_id)

    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


###


@app.route("/api/v3/admin/authentication/providers", methods=["GET"])
@is_admin
def admin_authentication_providers(payload):
    providers = get_providers()
    return (
        json.dumps(providers),
        200,
        {"Content-Type": "application/json"},
    )
