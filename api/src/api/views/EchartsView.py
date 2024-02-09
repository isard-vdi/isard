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

from cachetools import TTLCache, cached
from flask import request

from api import app

from ..libv2.echarts import (
    get_daily_items,
    get_grouped_data,
    get_grouped_unique_data,
    get_nested_array_grouped_data,
)
from .decorators import is_admin


@cached(cache=TTLCache(maxsize=10, ttl=60))
@app.route("/api/v3/admin/echart/<view>", methods=["POST"])
@is_admin
def api_v3_echarts(payload, view="raw"):
    data = request.get_json(force=True)
    if view == "daily_items":
        return (
            json.dumps(
                get_daily_items(data.get("table"), data.get("date_field")),
                indent=4,
                sort_keys=True,
                default=str,
            ),
            200,
            {"Content-Type": "application/json"},
        )
    if view == "grouped_items":
        return (
            json.dumps(
                get_grouped_data(data.get("table"), data.get("group_field")),
                indent=4,
                sort_keys=True,
                default=str,
            ),
            200,
            {"Content-Type": "application/json"},
        )
    if view == "grouped_unique_items":
        return (
            json.dumps(
                get_grouped_unique_data(
                    data.get("table"), data.get("group_field"), data.get("unique_field")
                ),
                indent=4,
                sort_keys=True,
                default=str,
            ),
            200,
            {"Content-Type": "application/json"},
        )
    if view == "nested_array_grouped_items":
        return (
            json.dumps(
                get_nested_array_grouped_data(
                    data.get("table"),
                    data.get("nested_array_field"),
                    data.get("group_field"),
                ),
                indent=4,
                sort_keys=True,
                default=str,
            ),
            200,
            {"Content-Type": "application/json"},
        )
