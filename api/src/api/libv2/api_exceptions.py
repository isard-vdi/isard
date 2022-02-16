import inspect
import logging as log
import os
import traceback

from flask import jsonify

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
}


class Error(Exception):
    def __init__(self, error="bad_request", description="", debug="", request=None):
        self.error = ex[error]["error"].copy()
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
        self.error["debug"] = "{}\n\r{}".format(
            "----------- DEBUG START -------------", debug
        )
        self.error["request"] = (
            "{}\n{}\r\n{}\r\n\r\n{}".format(
                "----------- REQUEST START -----------",
                request.method + " " + request.url,
                "\r\n".join("{}: {}".format(k, v) for k, v in request.headers.items()),
                request.body if hasattr(request, "body") else "",
            )
            if request
            else ""
        )
        self.status_code = ex[error]["status_code"]
        self.content_type = content_type
        log.debug(app.sm(self.error))


@app.errorhandler(Error)
def handle_user_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    response.headers = {"content-type": content_type}
    return response
