#
#   Copyright © 2024 Pau Abril Iranzo
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
import logging as log
import traceback

from flask import request
from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.api_media import get_media, get_status
from ..libv2.helpers import get_user_data
from .decorators import has_token, is_admin_or_manager, ownsMediaId, ownsStorageId


@app.route("/api/v3/media/status", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_media_status(payload):
    return (
        json.dumps(
            get_status(
                payload["category_id"] if payload["role_id"] == "manager" else None
            )
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/media", methods=["GET"])
@app.route("/api/v3/admin/media/<status>", methods=["GET"])
@is_admin_or_manager
def api_v3_admin_media(payload, status=None):
    media = get_media(
        status=status,
        category_id=payload["category_id"] if payload["role_id"] == "manager" else None,
    )
    return (
        json.dumps(media),
        200,
        {"Content-Type": "application/json"},
    )
