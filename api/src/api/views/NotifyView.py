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
from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.api_desktops_common import ApiDesktopsCommon
from ..libv2.api_notify import notify_custom, notify_desktop, notify_user
from ..libv2.validators import _validate_item
from .decorators import has_token, is_admin

desktops = ApiDesktopsCommon()


@app.route("/api/v3/admin/notify/user/desktop", methods=["POST"])
@is_admin
def user_notify(payload):
    data = request.get_json()
    notify_user(
        data["user_id"],
        data["type"],
        data.get("msg_code"),
        data.get("params"),
    )
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/notify/desktop", methods=["POST"])
@is_admin
def desktop_notify(payload):
    data = request.get_json()
    notify_desktop(
        data["desktop_id"],
        data["type"],
        data.get("msg_code"),
        data.get("params"),
    )
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/notify/desktops/queue", methods=["PUT"])
@is_admin
def desktop_notify_queue(payload):
    try:
        data = request.get_json()
    except:
        raise Error("bad_request")
    data = _validate_item("desktop_queues", {"items": data})["items"]

    users, categories = desktops.parse_desktop_queues(data)

    for user_id, user_desktops in users.items():
        notify_custom("desktops_queue", user_desktops, "/userspace", user_id)

    for category_id, category_desktops in categories.items():
        notify_custom(
            "desktops_queue", category_desktops, "/administrators", category_id
        )

    notify_custom("desktops_queue", data, "/administrators", "admins")

    return json.dumps({}), 200, {"Content-Type": "application/json"}
