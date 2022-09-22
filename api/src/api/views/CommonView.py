# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import traceback

from api import app

from ..libv2.api_exceptions import Error
from ..libv2.api_templates import ApiTemplates
from ..libv2.quotas import Quotas

templates = ApiTemplates()
quotas = Quotas()

from ..libv2.api_admin import admin_table_get
from ..libv2.api_desktops_common import ApiDesktopsCommon

common = ApiDesktopsCommon()

from ..libv2.api_allowed import ApiAllowed

allowed = ApiAllowed()

from ..libv2.helpers import _get_domain_reservables
from .decorators import has_token, ownsDomainId


@app.route("/api/v3/desktop/<desktop_id>/viewer/<protocol>", methods=["GET"])
@has_token
def api_v3_desktop_viewer(payload, desktop_id=False, protocol=False):
    if desktop_id == False or protocol == False:
        raise Error(
            "bad_request",
            "Desktop viewer incorrect body data",
            traceback.format_exc(),
            description_code="incorrect_viewer_body_data",
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
@app.route("/api/v3/domains/allowed/<kind>/<domain_id>", methods=["GET"])
@has_token
def api_v3_domains_allowed_hardware_reservables(payload, kind, domain_id=None):
    if kind == "reservables":
        if domain_id and ownsDomainId(payload, domain_id):
            domain_reservables_vgpus = _get_domain_reservables(domain_id)["vgpus"]
            reservables = {
                "vgpus": allowed.get_items_allowed(
                    payload,
                    "reservables_vgpus",
                    query_pluck=["id", "name", "description"],
                    order="name",
                    query_merge=False,
                    extra_ids_allowed=domain_reservables_vgpus,
                )
            }
            return json.dumps(reservables)
        else:
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


# Will get allowed hardware quota max resources for different items
@app.route("/api/v3/quota/<kind>", methods=["GET"])
@app.route("/api/v3/quota/<kind>/<item_id>", methods=["GET"])
@has_token
def user_quota_max(payload, kind, item_id=None):
    if kind == "user":
        if not item_id:
            item_id = payload["user_id"]
        return json.dumps(quotas.GetUserQuota(item_id))
    if kind == "category":
        if not item_id:
            item_id = payload["category_id"]
        return json.dumps(quotas.GetCategoryQuota(item_id))
    if kind == "group":
        if not item_id:
            item_id = payload["group_id"]
        return json.dumps(quotas.GetGroupQuota(item_id))


@app.route("/api/v3/domain/info/<domain_id>", methods=["GET"])
@has_token
def api_v3_desktop_info(payload, domain_id):
    domain = {
        **admin_table_get(
            "domains",
            pluck=["id", "kind", "name", "description", "image", "guest_properties"],
            id=domain_id,
        ),
        **common.get_domain_hardware(domain_id),
    }
    if domain["kind"] == "template":
        template = templates.Get(domain_id)
        allowed.is_allowed(payload, template, "domains")
    else:
        ownsDomainId(payload, domain_id)
    domain = quotas.limit_user_hardware_allowed(payload, domain)
    return (
        json.dumps(domain),
        200,
        {"Content-Type": "application/json"},
    )
