# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import datetime
import logging
import os
import time

from flask import g, request
from flask.logging import default_handler
from jose import jwt
from pythonjsonlogger import jsonlogger

from api import app


class RequestFormatter(jsonlogger.JsonFormatter):
    def format(self, record):
        record.levelname = record.levelname.lower()

        return super().format(record)

    @staticmethod
    def formatTime(record, datefmt=None):
        # Format record.created as RFC3339
        return (
            datetime.datetime.fromtimestamp(record.created)
            .replace(microsecond=0)
            .astimezone()
            .isoformat()
        )


def parse_data(request):
    try:
        data = request.get_json(force=True)
    except Exception:
        data = dict(request.form) if len(dict(request.form)) else dict(request.args)

    if request.method not in ["POST", "PUT"]:
        return data

    if type(data) is not dict:
        return data

    if data.get("password"):
        data["password"] = "****"
        return data

    if data.get("code"):
        data["code"] = "****"
        return data

    if data.get("guest_properties", {}).get("credentials", {}).get("password"):
        data["guest_properties"]["credentials"]["password"] = "****"
        return data

    if data.get("image", {}).get("file", {}).get("data"):
        data["image"]["file"]["data"] = "[binary removed]"
        return data

    return data


@app.before_request
def start_timer():
    g.start = time.time()


@app.after_request
def log_request(response):
    now = time.time()
    duration = round(now - g.start, 4)

    remote_addr = (
        request.headers["X-Forwarded-For"].split(",")[0]
        if "X-Forwarded-For" in request.headers
        else request.remote_addr.split(",")[0]
    )

    extra = {}
    try:
        claims = jwt.get_unverified_claims(
            request.headers.get("Authorization", None).split()[1]
        )

        extra = {
            **extra,
            "kid": claims.get("kid"),
            "iss": claims.get("iss"),
            "category_id": claims.get("data", {}).get("category_id"),
            "group_id": claims.get("data", {}).get("group_id"),
            "user_id": claims.get("data", {}).get("user_id"),
            "role_id": claims.get("data", {}).get("role_id"),
        }

    except Exception:
        pass

    data = parse_data(request)
    if data != {}:
        extra = {**extra, "data": data}

    app.logger.info(
        "response served",
        extra={
            **extra,
            "duration": duration,
            "status": response._status_code,
            "path": request.path,
            "method": request.method,
            "remote_addr": remote_addr,
        },
    )

    return response


# Disable Flask loggers, we're going to use ours
logging.getLogger("werkzeug").disabled = True
logging.getLogger("geventwebsocket.handler").disabled = True

# Get log level
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")
LOG_LEVEL_NUM = logging.getLevelName(LOG_LEVEL)

# Configure log formatter
formatter = RequestFormatter(
    "%(levelname)s %(service)s %(message)s %(asctime)s",
    rename_fields={
        "message": "msg",
        "levelname": "level",
        "asctime": "time",
    },
    static_fields={"service": "api"},
)

# Configure global logger
logger = logging.getLogger()
handler = logging.StreamHandler()
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(LOG_LEVEL_NUM)

# Configure flask logger
default_handler.setFormatter(formatter)
