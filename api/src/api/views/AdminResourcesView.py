# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log

from flask import request
from isardvdi_common.api_exceptions import Error

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2.api_resources import add_qos_disk, check_qos_burst_limits, update_qos_disk
from ..libv2.isardVpn import isardVpn
from ..libv2.validators import _validate_item
from .decorators import checkDuplicate, is_admin

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


@app.route("/api/v3/qos_disk/", methods=["POST"])
@is_admin
def api_v3_qos_disk_add(payload):
    data = request.get_json()
    checkDuplicate("qos_disk", data["name"])
    data = _validate_item("qos_disk", data)
    errors = check_qos_burst_limits(data.get("iotune"))
    if errors:
        return (
            json.dumps({"errors": errors}),
            400,
            {"Content-Type": "application/json"},
        )
    else:
        add_qos_disk(data)
        return (
            json.dumps({}),
            200,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/qos_disk", methods=["PUT"])
@is_admin
def api_v3_qos_disk_update(payload):
    data = request.get_json()
    checkDuplicate("qos_disk", data["name"], item_id=data["id"])
    qos_disk_id = data["id"]
    data = _validate_item("qos_disk_update", data)
    errors = check_qos_burst_limits(data.get("iotune"))
    if errors:
        return (
            json.dumps({"errors": errors}),
            400,
            {"Content-Type": "application/json"},
        )
    else:
        update_qos_disk(qos_disk_id, data)
        return (
            json.dumps({}),
            200,
            {"Content-Type": "application/json"},
        )
