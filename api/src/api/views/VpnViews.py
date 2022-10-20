# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import traceback

from flask import request

from api import app

from ..libv2.api_exceptions import Error
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_vpn import (
    active_client,
    reset_connection_status,
    reset_connections_list_status,
)
from .decorators import is_admin


@app.route(
    "/api/v3/vpn_connection/<kind>/<client_ip>", methods=["POST", "PUT"]
)  # POST: Connected, PUT: Roamed
@app.route(
    "/api/v3/vpn_connection/<kind>/<client_ip>", methods=["DELETE"]
)  # Disconnected
@app.route(
    "/api/v3/vpn_connection/<kind>", methods=["DELETE"]
)  # Initial reset of all connections
@is_admin
def api_v3_vpn_connection(payload, kind, client_ip=None):
    if request.method in ["POST", "PUT"]:
        try:
            remote_ip = request.form.get("remote_ip", type=str)
            remote_port = request.form.get("remote_port", type=int)
        except:
            raise Error(
                "bad_request",
                "Vpn connection bad body data",
                traceback.format_exc(),
            )

        if remote_ip == None or remote_port == None:
            raise Error(
                "bad_request",
                "Vpn connection incorrect body data",
                traceback.format_exc(),
            )
        if active_client(kind, client_ip, remote_ip, remote_port, True):
            log.debug(kind + "-" + client_ip + "-true")
            return (
                json.dumps({}),
                200,
                {"Content-Type": "application/json"},
            )
        raise Error(
            "internal_server",
            "Update vpn connection failed",
            traceback.format_exc(),
        )
    if request.method == "DELETE":
        if client_ip:
            return (
                json.dumps(active_client(kind, client_ip)),
                200,
                {"Content-Type": "application/json"},
            )
        elif kind == "all":
            if reset_connection_status(kind):
                return json.dumps({}), 200, {"Content-Type": "application/json"}
        raise Error(
            "internal_server",
            "Update vpn connection failed",
            traceback.format_exc(),
        )
    raise Error("bad_request", "Incorrect access method", traceback.format_exc())


@app.route("/api/v3/vpn_connections", methods=["DELETE"])  # Disconnected
@is_admin
def api_v3_vpn_connections(payload):
    try:
        data = request.get_json(force=True)
    except:
        raise Error("bad_request", "Vpn connections delete bad data request")

    return (
        json.dumps(reset_connections_list_status(data)),
        200,
        {"Content-Type": "application/json"},
    )
