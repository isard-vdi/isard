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

from api import app

from ..libv2.api_admin import admin_table_list
from .decorators import is_admin


@app.route("/api/v3/admin/scheduler/jobs/system", methods=["GET"])
@is_admin
def api_v3_admin_scheduler_jobs_system(payload):
    return json.dumps(
        admin_table_list(
            "scheduler_jobs",
            order_by="next_run_time",
            pluck=["id", "name", "kind", "next_run_time"],
            index="system",
        )
    )


@app.route("/api/v3/admin/scheduler/jobs/bookings", methods=["GET"])
@is_admin
def api_v3_admin_scheduler_jobs_bookings(payload):
    return json.dumps(
        admin_table_list(
            "scheduler_jobs",
            order_by="next_run_time",
            pluck=["id", "name", "kind", "next_run_time", "kwargs"],
            index="bookings",
        )
    )
