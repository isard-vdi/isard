# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import traceback

from flask import request

from api import app

from ..libv2.apiv2_exc import *
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_vpn import ApiVpn, reset_connection_status

api_vpn = ApiVpn()

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
        except Exception as e:
            error = traceback.format_exc()
            return (
                json.dumps(
                    {
                        "error": "bad_request",
                        "msg": "Incorrect access. Exception: " + error,
                    }
                ),
                400,
                {"Content-Type": "application/json"},
            )
        if remote_ip == None or remote_port == None:
            log.error("Incorrect access parameters. Check your query.")
            return (
                json.dumps(
                    {
                        "error": "bad_request",
                        "msg": "Incorrect access parameters. Check your query.",
                    }
                ),
                400,
                {"Content-Type": "application/json"},
            )

        try:
            if api_vpn.active_client(kind, client_ip, remote_ip, remote_port, True):
                log.debug(kind + "-" + client_ip + "-true")
                return (
                    json.dumps({}),
                    200,
                    {"Content-Type": "application/json"},
                )
            else:
                log.debug(kind + "-" + client_ip + "-false")
                return (
                    json.dumps({}),
                    400,
                    {"Content-Type": "application/json"},
                )
        except Exception as e:
            return (
                json.dumps(
                    {
                        "error": "generic_error",
                        "msg": "Exception: " + traceback.format_exc(),
                    }
                ),
                500,
                {"Content-Type": "application/json"},
            )

    if request.method == "DELETE":
        try:
            if client_ip:
                try:
                    return (
                        json.dumps(api_vpn.active_client(kind, client_ip)),
                        200,
                        {"Content-Type": "application/json"},
                    )
                except:
                    log.error(traceback.format_exc())
                    return (
                        json.dumps(
                            {
                                "error": "generic_error",
                                "msg": "Exception: " + traceback.format_exc(),
                            }
                        ),
                        500,
                        {"Content-Type": "application/json"},
                    )
            elif kind == "all":
                try:
                    if reset_connection_status(kind):
                        return json.dumps({}), 200, {"Content-Type": "application/json"}
                    else:
                        log.debug(kind + "-" + client_ip + "-false")
                        return (
                            json.dumps({}),
                            401,
                            {"Content-Type": "application/json"},
                        )
                except:
                    log.error(traceback.format_exc())
                    return (
                        json.dumps(
                            {
                                "error": "generic_error",
                                "msg": "Exception: " + traceback.format_exc(),
                            }
                        ),
                        500,
                        {"Content-Type": "application/json"},
                    )
        except:
            return (
                json.dumps(
                    {
                        "error": "generic_error",
                        "msg": "Incorrect access. exception: " + traceback.format_exc(),
                    }
                ),
                500,
                {"Content-Type": "application/json"},
            )
