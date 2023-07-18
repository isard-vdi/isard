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
from .decorators import is_admin


@cached(cache=TTLCache(maxsize=1, ttl=5))
@app.route("/api/v3/maintenance", methods=["GET"])
def _api_maintenance_get():
    return (
        json.dumps(Maintenance.enabled),
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
