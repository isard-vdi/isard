#
#   Copyright © 2022 Simó Albert i Beltran
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

from cachetools import TTLCache, cached
from flask import request

from api import app

from ..libv2.maintenance import Maintenance
from ..libv2.validators import _validate_item
from .decorators import get_category_maintenance, has_token, is_admin, maintenance


@cached(cache=TTLCache(maxsize=1, ttl=5))
@app.route("/api/v3/maintenance/status", methods=["GET"])
def _api_maintenance_get_status():
    return (
        json.dumps(Maintenance.enabled),
        200,
        {"Content-Type": "application/json"},
    )


@cached(cache=TTLCache(maxsize=1, ttl=5))
@app.route("/api/v3/maintenance", methods=["GET"])
@app.route("/api/v3/maintenance/<category_id>", methods=["GET"])
@has_token
def _api_maintenance_get(payload, category_id=None):
    status = Maintenance.enabled
    category_status = get_category_maintenance(
        category_id if category_id else payload["category_id"]
    )
    return (
        json.dumps(status or category_status),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/maintenance", methods=["PUT"])
@is_admin
def _api_maintenance_put(payload):
    Maintenance.enabled = request.get_json()
    return (
        json.dumps(Maintenance.enabled),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/maintenance/text", methods=["PUT"])
@is_admin
def _api_maintenance_text_put(payload):
    data = request.get_json()

    data = _validate_item("maintenance_text", data)
    return (
        json.dumps(Maintenance.update_text(data)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/maintenance/text", methods=["GET"])
@is_admin
def _api_maintenance_text_get(payload):
    return (
        json.dumps(Maintenance.get_text()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/maintenance/text/frontend", methods=["GET"])
def _api_maintenance_text_frontend_get():
    if Maintenance.enabled:
        return (
            json.dumps(Maintenance.get_text()),
            200,
            {"Content-Type": "application/json"},
        )
    else:
        return (
            json.dumps({}),
            204,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/maintenance/text/enable/<set_custom>", methods=["PUT"])
@is_admin
def _api_maintenance_text_enable(payload, set_custom):
    set_custom = set_custom == "true"
    return (
        json.dumps(Maintenance.enable_custom_text(set_custom)),
        200,
        {"Content-Type": "application/json"},
    )
