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

import inspect
import json
import logging as log
import os

from flask import jsonify, request

from api import app

content_type = {"Content-Type": "application/json"}
ex = {
    "bad_request": {
        "error": {
            "error": "bad_request",
            "msg": "Bad request",
        },
        "status_code": 400,
    },
    "unauthorized": {
        "error": {
            "error": "unauthorized",
            "msg": "Unauthorized",
        },
        "status_code": 401,
    },
    "forbidden": {
        "error": {
            "error": "forbidden",
            "msg": "Forbidden",
        },
        "status_code": 403,
    },
    "not_found": {
        "error": {
            "error": "not_found",
            "msg": "Not found",
        },
        "status_code": 404,
    },
    "conflict": {
        "error": {
            "error": "conflict",
            "msg": "Conflict",
        },
        "status_code": 409,
    },
    "internal_server": {
        "error": {
            "error": "internal_server",
            "msg": "Internal server error",
        },
        "status_code": 500,
    },
    "gateway_timeout": {
        "error": {
            "error": "gateway_timeout",
            "msg": "Gateway timeout",
        },
        "status_code": 504,
    },
    "precondition_required": {
        "error": {
            "error": "precondition_required",
            "msg": "Precondition required",
        },
        "status_code": 428,
    },
    "insufficient_storage": {
        "error": {
            "error": "insufficient_storage",
            "msg": "Insufficient storage",
        },
        "status_code": 507,
    },
}


class Error(Exception):
    def __init__(
        self,
        error="bad_request",
        description="",
        debug=False,
        description_code=None,
        data=None,
        params=None,
    ):
        # NOTE: Description codes are defined at https://gitlab.com/isard/isardvdi/-/blob/main/frontend/src/locales/en.json#L340
        self.error = ex[error]["error"].copy()
        self.error["description_code"] = description_code if description_code else error
        self.error["function"] = (
            inspect.stack()[1][1].split(os.sep)[-1]
            + ":"
            + str(inspect.stack()[1][2])
            + ":"
            + inspect.stack()[1][3]
        )
        self.error["function_call"] = (
            inspect.stack()[2][1].split(os.sep)[-1]
            + ":"
            + str(inspect.stack()[2][2])
            + ":"
            + inspect.stack()[2][3]
        )
        self.error["description"] = str(description)
        self.error["debug"] = (
            "{}\n\r{}{}".format(
                "----------- DEBUG START -------------",
                debug,
                "----------- DEBUG STOP  -------------",
            )
            if debug
            else ""
        )
        self.error["request"] = (
            "{}\n{}\r\n{}\r\n\r\n{}{}".format(
                "----------- REQUEST START -----------",
                request.method + " " + request.url,
                "\r\n".join("{}: {}".format(k, v) for k, v in request.headers.items()),
                request.body if hasattr(request, "body") else "",
                "----------- REQUEST STOP  -----------",
            )
            if request
            else ""
        )
        self.error["data"] = (
            "{}\n{}\n{}".format(
                "----------- DATA START   -----------",
                json.dumps(data, indent=2),
                "----------- DATA STOP    -----------",
            )
            if data
            else ""
        )
        self.status_code = ex[error]["status_code"]
        self.content_type = content_type
        self.error["params"] = params
        log.debug(
            "%s - %s - [%s -> %s]\r\n%s\r\n%s\r\n%s"
            % (
                error,
                str(description),
                self.error["function_call"],
                self.error["function"],
                self.error["debug"],
                self.error["request"],
                self.error["data"],
            )
        )


@app.errorhandler(Error)
def handle_user_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    response.headers = {"content-type": content_type}
    return response
