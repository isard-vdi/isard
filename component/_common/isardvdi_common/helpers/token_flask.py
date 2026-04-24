#
#   Copyright © 2023 Josep Maria Viñolas Auquer
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


import gevent
from flask import request
from isardvdi_common.helpers.api_exceptions_flask import Error
from isardvdi_common.helpers.api_logs_users import LogsUsers
from isardvdi_common.helpers.token import Token


class TokenFlask(Token):

    @staticmethod
    def get_token_header(header):
        """Obtains the Access Token from the a Header"""
        auth = request.headers.get(header, None)
        if not auth:
            raise Error(
                "unauthorized",
                header + " header is expected",
            )

        parts = auth.split()
        if parts[0].lower() != "bearer":
            raise Error(
                "unauthorized",
                header + " header must start with Bearer",
            )
        elif len(parts) == 1:
            raise Error("bad_request", "Token not found")
        elif len(parts) > 2:
            raise Error(
                "unauthorized",
                header + " header must be Bearer token",
            )

        return parts[1]  # Token

    @classmethod
    def log_user(cls, payload):
        try:
            gevent.spawn(LogsUsers, payload)
        except Exception as e:
            log.warning("Unable to update user logs")
