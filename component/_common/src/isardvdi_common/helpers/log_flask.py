# coding=utf-8
# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import logging
import os
import time
from importlib import import_module
from importlib.util import find_spec
from pprint import pformat

import jwt
import simple_colors as sc
from flask import g, request
from flask.logging import default_handler
from isardvdi_common.helpers.log import LOG_LEVEL, formatter

for module in ["api", "webapp", "scheduler", "notifier"]:
    if find_spec(f"{module}"):
        app = import_module(f"{module}").app
        break


def parse_data(request):
    try:
        data = request.get_json(force=True)
    except Exception:
        data = dict(request.form) if len(dict(request.form)) else dict(request.args)

    if request.method not in ["POST", "PUT"]:
        return data

    if type(data) is not dict:
        return data

    if data.get("current_password"):
        data["current_password"] = "****"
        data["password"] = "****"
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
    if LOG_LEVEL == "DEBUG":
        # Suppress noisy stats polling and socket.io frames from the
        # debug log unless explicitly asked for via env.
        if os.environ.get("DEBUG_STATS", "") != "true":
            if request.path.startswith("/api/v4/stats") or request.path == "/api/v4":
                return response
        if os.environ.get("DEBUG_WEBSOCKETS", "") != "true":
            if request.path.startswith("/socket.io"):
                return response

    now = time.time()
    duration = round(now - g.start, 4)

    remote_addr = (
        request.headers["X-Forwarded-For"].split(",")[0]
        if "X-Forwarded-For" in request.headers
        else request.remote_addr.split(",")[0]
    )

    extra = {}
    try:
        claims = jwt.decode(
            request.headers.get("Authorization", None).split()[1],
            options={"verify_signature": False},
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

    log_data = {
        **extra,
        "duration": duration,
        "status": response._status_code,
        "path": request.path,
        "method": request.method,
        "remote_addr": remote_addr,
    }

    if LOG_LEVEL == "DEBUG":
        print(
            (
                sc.green(response._status_code, "reverse")
                if response._status_code == 200
                else sc.red(response._status_code, "reverse")
            ),
            (
                sc.green(request.method, "reverse")
                if request.method == "GET"
                else (
                    sc.blue(request.method, "reverse")
                    if request.method == "POST"
                    else (
                        sc.yellow(request.method, "reverse")
                        if request.method == "PUT"
                        else (
                            sc.red(request.method, "reverse")
                            if request.method == "DELETE"
                            else sc.magenta(request.method, "reverse")
                        )
                    )
                )
            ),
            (
                sc.green(request.path, "reverse")
                if response._status_code == 200
                else sc.red(request.path, "reverse")
            ),
            (
                sc.green(f"{duration}s", "reverse")
                if duration < 0.05
                else (
                    sc.yellow(f"{duration}s", "reverse")
                    if duration < 0.1
                    else (
                        sc.blue(f"{duration}s", "reverse")
                        if duration < 0.25
                        else (
                            sc.magenta(f"{duration}s", "reverse")
                            if duration < 0.5
                            else sc.red(f"{duration}s", "reverse")
                        )
                    )
                )
            ),
        )
        if extra.get("data"):
            print(sc.cyan(pformat(extra["data"]), "reverse"))

    app.logger.info(
        "response served",
        extra=log_data,
    )

    return response


# Disable Flask loggers, we're going to use ours
logging.getLogger("werkzeug").disabled = True
logging.getLogger("geventwebsocket.handler").disabled = True

# Configure flask logger
default_handler.setFormatter(formatter)
