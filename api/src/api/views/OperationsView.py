#
#   Copyright © 2025 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

from api import app

from ..libv2.api_operations import list_hypervisors, start_hypervisor, stop_hypervisor
from .decorators import is_admin


@app.route("/api/v3/operations/hypervisors", methods=["GET"])
@is_admin
def api_v3_operations_hypervisors(payload):
    return (
        json.dumps(list_hypervisors()),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/operations/hypervisor/<hypervisor_id>", methods=["PUT"])
@is_admin
def api_v3_operations_hypervisor_start(payload, hypervisor_id):
    return (
        json.dumps(start_hypervisor(hypervisor_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/operations/hypervisor/<hypervisor_id>", methods=["DELETE"])
@is_admin
def api_v3_operations_hypervisor_stop(payload, hypervisor_id):
    return (
        json.dumps(stop_hypervisor(hypervisor_id)),
        200,
        {"Content-Type": "application/json"},
    )
