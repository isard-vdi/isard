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

import traceback
from functools import wraps

from flask import abort, request

from api import app

from .._common.api_exceptions import Error
from .._common.tokens import Error, get_header_jwt_payload


def has_token(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        kwargs["payload"] = payload
        return f(*args, **kwargs)

    return decorated


def is_admin(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload["role_id"] == "admin":
            kwargs["payload"] = payload
            return f(*args, **kwargs)
        raise Error(
            "forbidden",
            "Not enough rights.",
            traceback.format_exc(),
            description_code="forbidden",
        )

    return decorated


def is_admin_or_manager(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        payload = get_header_jwt_payload()
        if payload["role_id"] == "admin" or payload["role_id"] == "manager":
            kwargs["payload"] = payload
            return f(*args, **kwargs)
        raise Error(
            "forbidden",
            "Not enough rights.",
            traceback.format_exc(),
        )

    return decorated
