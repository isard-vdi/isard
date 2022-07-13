# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import traceback

from api import app

from ..libv2.api_exceptions import Error
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_desktops_common import ApiDesktopsCommon

common = ApiDesktopsCommon()

from ..libv2.api_allowed import ApiAllowed

allowed = ApiAllowed()

from .decorators import has_token, ownsDomainId


@app.route("/api/v3/desktop/<desktop_id>/viewer/<protocol>", methods=["GET"])
@has_token
def api_v3_desktop_viewer(payload, desktop_id=False, protocol=False):
    if desktop_id == False or protocol == False:
        raise Error(
            "bad_request",
            "Desktop viewer incorrect body data",
            traceback.format_exc(),
        )

    ownsDomainId(payload, desktop_id)
    return (
        json.dumps(common.DesktopViewer(desktop_id, protocol, get_cookie=True)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktop/<desktop_id>/viewers", methods=["GET"])
@has_token
def api_v2_desktop_viewers(payload, desktop_id=False, protocol=False):
    ownsDomainId(payload, desktop_id)
    viewers = []
    for protocol in ["browser-vnc", "file-spice"]:
        viewer = common.DesktopViewer(desktop_id, protocol, get_cookie=True)
        viewers.append(viewer)
    return json.dumps(viewers), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/domains/allowed/<kind>", methods=["GET"])
@has_token
def api_v3_domains_allowed_hardware_reservables(payload, kind):
    if kind == "reservables":
        reservables = {}
        reservables["vgpus"] = allowed.get_items_allowed(
            payload,
            "reservables_vgpus",
            query_pluck=["id", "name", "description"],
            order="name",
            query_merge=False,
        )
        return json.dumps(reservables)
    if kind == "hardware":
        return Error("bad_request", "Not implemented")


@app.route("/api/v3/domains/allowed/<kind>/defaults/<domain_id>", methods=["GET"])
@has_token
def api_v3_domains_default_hardware_reservables(payload, kind, domain_id):
    ownsDomainId(payload, domain_id)
    if kind == "reservables":
        return json.dumps(allowed.get_domain_reservables(domain_id))
    if kind == "hardware":
        return Error("bad_request", "Not implemented")


@app.route("/api/v3/domain/hardware/<desktop_id>", methods=["GET"])
@has_token
def api_v3_desktop_hardware(payload, desktop_id):
    ownsDomainId(payload, desktop_id)
    return (
        json.dumps(common.get_domain_hardware(desktop_id)),
        200,
        {"Content-Type": "application/json"},
    )
