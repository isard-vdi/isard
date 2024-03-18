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

from flask import has_request_context, jsonify, request

try:
    from api import app
except:
    try:
        from webapp import app
    except:
        try:
            from scheduler import app
        except:
            from notifier import app

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

ex_codes = [ex[x]["status_code"] for x in ex]


class RequestObj:
    # Used when requests are being done outside flask context
    # For example in whithin a thread from the same app, not from client
    def __init__(self, method="", url="", data=None, headers=None):
        self.method = method
        self.url = url
        if data:
            self.body = data
        if headers:
            self.headers = headers


class Error(Exception):
    def __init__(
        self,
        error="bad_request",
        description="",
        debug=False,
        description_code=None,
        data=None,
        params=None,
        custom_request=None,
    ):
        if custom_request:
            self.request = custom_request
        else:
            if has_request_context():
                self.request = request
            else:
                self.request = RequestObj()
        # NOTE: Description codes are defined at https://gitlab.com/isard/isardvdi/-/blob/main/frontend/src/locales/en.json#L340
        self.error = ex[error]["error"].copy()
        self.error["description_code"] = description_code if description_code else error
        self.error["function"] = (
            (
                inspect.stack()[1][1].split(os.sep)[-1]
                + ":"
                + str(inspect.stack()[1][2])
                + ":"
                + inspect.stack()[1][3]
            )
            if debug
            else ""
        )
        try:
            self.error["function_call"] = (
                (
                    inspect.stack()[2][1].split(os.sep)[-1]
                    + ":"
                    + str(inspect.stack()[2][2])
                    + ":"
                    + inspect.stack()[2][3]
                )
                if debug
                else ""
            )
        except:
            self.error["function_call"] = "-"
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
                self.request.method + " " + self.request.url,
                (
                    "\r\n".join(
                        "{}: {}".format(k, v) for k, v in self.request.headers.items()
                    )
                    if hasattr(self.request, "headers")
                    else ""
                ),
                self.request.body if hasattr(self.request, "body") else "",
                "----------- REQUEST STOP  -----------",
            )
            if self.request and debug
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
        if self.status_code in ex_codes:
            if error == "unauthorized":
                url = self.request.url.split("/?jwt=")
                if len(url) > 1:
                    # It's a websocket connection
                    if not os.environ.get("DEBUG_WEBSOCKETS", "") == "true":
                        return
                app.logger.error(
                    error,
                    extra={
                        "status": self.status_code,
                        "error": self.error.get("description"),
                        "error_type": error,
                        "request": {
                            "method": (
                                self.request.method
                                if hasattr(self.request, "method")
                                else ""
                            ),
                            "url": url[0],
                        },
                        "data": data if data else "",
                    },
                )
            else:
                extra = {
                    "status": self.status_code,
                    "error": self.error.get("description"),
                    "error_type": error,
                    "function_call": "[%s -> %s]"
                    % (self.error.get("function_call"), self.error.get("function")),
                    "request": {
                        "url": self.request.url if hasattr(self.request, "url") else "",
                    },
                }
                if os.environ.get("LOG_LEVEL", "INFO") == "DEBUG":
                    if hasattr(self.request, "headers"):
                        extra["request"]["headers"] = self.request.headers
                    if debug:
                        extra["debug"] = debug

                if hasattr(self.request, "method"):
                    extra["request"]["method"] = self.request.method
                if hasattr(self.request, "body"):
                    extra["request"]["body"] = self.request.body
                if data:
                    extra["data"] = data
                app.logger.error(
                    error,
                    extra=extra,
                )


@app.errorhandler(Error)
def handle_user_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    response.headers = {"content-type": content_type}
    return response
