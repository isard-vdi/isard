# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log

from isardvdi_common.api_exceptions import Error

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.isardVpn import isardVpn
from .decorators import is_admin

vpn = isardVpn()


@app.route("/api/v3/remote_vpn/<vpn_id>/<kind>/<os>", methods=["GET"])
@app.route("/api/v3/remote_vpn/<vpn_id>/<kind>", methods=["GET"])
# kind = config,install
# os =
@is_admin
def api_v3_remote_vpn(payload, vpn_id, kind="config", os=False):
    if not os and kind != "config":
        raise Error("bad_request", "RemoteVpn: no OS supplied")

    return (
        json.dumps(vpn.vpn_data("remotevpn", kind, os, vpn_id)),
        200,
        {"Content-Type": "application/json"},
    )
