#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2023 Simó Albert i Beltran
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from flask import jsonify, request
from isardvdi_common.api_exceptions import Error

from api import app, socketio

from .decorators import is_admin


@app.route("/api/v3/socketio", methods=["POST"])
@is_admin
def emit_socketio(payload):
    """
    Endpoint to send a socketio message.

    :param payload: Data from JWT
    :type payload: dict
    :return: True
    :rtype: flask.Response
    """
    if not request.is_json:
        raise Error(description="JSON expected")
    socketio.emit(**request.json)
    return jsonify(True)
