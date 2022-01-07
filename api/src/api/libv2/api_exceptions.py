import inspect
import logging as log
import traceback

from flask import jsonify

from api import app

ex = {
    "bad_request": {
        "error": {
            "error": "bad_request",
            "msg": "Bad request",
        },
        "status_code": 400,
        "content_type": {"Content-Type": "application/json"},
    },
    "unauthorized": {
        "error": {
            "error": "unauthorized",
            "msg": "Unauthorized",
        },
        "status_code": 401,
        "content_type": {"Content-Type": "application/json"},
    },
    "forbidden": {
        "error": {
            "error": "forbidden",
            "msg": "Forbidden",
        },
        "status_code": 403,
        "content_type": {"Content-Type": "application/json"},
    },
    "not_found": {
        "error": {
            "error": "not_found",
            "msg": "Not found",
        },
        "status_code": 404,
        "content_type": {"Content-Type": "application/json"},
    },
    "conflict": {
        "error": {
            "error": "conflict",
            "msg": "Conflict",
        },
        "status_code": 409,
        "content_type": {"Content-Type": "application/json"},
    },
    "internal_server": {
        "error": {
            "error": "internal_server",
            "msg": "Internal server error",
        },
        "status_code": 500,
        "content_type": {"Content-Type": "application/json"},
    },
    "gateway_timeout": {
        "error": {
            "error": "gateway_timeout",
            "msg": "Gateway timeout",
        },
        "status_code": 504,
        "content_type": {"Content-Type": "application/json"},
    },
}


class AuthError(Exception):
    def __init__(self, error="bad_request", description="", debug="", request=None):
        self.error = ex[error]["error"].copy()
        self.error["type"] = "AUTH"
        self.error["function"] = inspect.stack()[1].function
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
        # self.error["debug"] = traceback.format_stack() #str(debug)
        self.status_code = ex[error]["status_code"]
        self.content_type = ex[error]["content_type"]
        log.warning(app.sm(self.error))
        log.debug(app.sm(self.error))


@app.errorhandler(AuthError)
def handle_auth_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    response.headers = {"content-type": ex.content_type}
    return response


class AdminError(Exception):
    def __init__(self, error="bad_request", description="", debug="", request=None):
        self.error = ex[error]["error"].copy()
        self.error["type"] = "ADMIN"
        self.error["function"] = inspect.stack()[1].function
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
        # self.error["debug"] = traceback.format_stack() #str(debug)
        self.status_code = ex[error]["status_code"]
        self.content_type = ex[error]["content_type"]
        log.warning(app.sm(self.error))
        log.debug(app.sm(self.error))


@app.errorhandler(AdminError)
def handle_admin_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    response.headers = {"content-type": ex.content_type}
    return response


class ValidateError(Exception):
    def __init__(self, error="bad_request", description="", debug="", request=None):
        self.error = ex[error]["error"].copy()
        self.error["type"] = "VALIDATE"
        self.error["function"] = inspect.stack()[1].function
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
        # self.error["debug"] = traceback.format_stack() #str(debug)
        self.status_code = ex[error]["status_code"]
        self.content_type = ex[error]["content_type"]
        log.warning(app.sm(self.error))
        log.debug(app.sm(self.error))


@app.errorhandler(ValidateError)
def handle_validate_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    response.headers = {"content-type": ex.content_type}
    return response


class UserError(Exception):
    def __init__(self, error="bad_request", description="", debug="", request=None):
        self.error = ex[error]["error"].copy()
        self.error["type"] = "USER"
        self.error["function"] = inspect.stack()[1].function
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
        # self.error["debug"] = traceback.format_stack() #str(debug)
        self.status_code = ex[error]["status_code"]
        self.content_type = ex[error]["content_type"]
        log.debug(app.sm(self.error))


@app.errorhandler(UserError)
def handle_user_error(ex):
    response = jsonify(ex.error)
    response.status_code = ex.status_code
    response.headers = {"content-type": ex.content_type}
    return response
