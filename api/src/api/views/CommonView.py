# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import traceback

from flask import request
from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.api_logging import logs_domain_event_viewer
from ..libv2.api_templates import ApiTemplates
from ..libv2.bookings.api_reservables import get_vgpus_hypervisors
from ..libv2.caches import get_document
from ..libv2.quotas import Quotas

templates = ApiTemplates()
quotas = Quotas()

from ..libv2.api_desktops_common import ApiDesktopsCommon

common = ApiDesktopsCommon()

from ..libv2.api_allowed import ApiAllowed

allowed = ApiAllowed()

from ..libv2.helpers import (
    _get_domain_reservables,
    change_owner_desktop,
    change_owner_media,
    change_owner_template,
)
from .decorators import (
    has_token,
    is_admin_or_manager,
    ownsDomainId,
    ownsMediaId,
    ownsUserId,
)


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
    logs_domain_event_viewer(
        desktop_id, payload["user_id"], protocol, user_request=request
    )
    if payload.get("role_id") and payload.get("role_id") == "admin":
        admin_role = True
    else:
        admin_role = False
    return (
        json.dumps(
            common.DesktopViewer(
                desktop_id, protocol, get_cookie=True, admin_role=admin_role
            )
        ),
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


def _attach_vgpu_hypervisor_groups(vgpus, show_names):
    """Tag each vGPU profile with the hypervisor groups that can host it.

    A multi-profile desktop must keep all its profiles on one hypervisor, so the
    UI needs to know which profiles share a host. Always attach
    ``hypervisor_groups`` (anonymized stable indices — two profiles are
    co-selectable iff their lists intersect). When ``show_names`` (admin/webapp)
    also attach the real ``hypervisors`` names for grouped labels.
    """
    hyp_map = get_vgpus_hypervisors()
    ordered_hyps = sorted({h for v in vgpus for h in hyp_map.get(v["id"], [])})
    anon_index = {h: i + 1 for i, h in enumerate(ordered_hyps)}
    for v in vgpus:
        hyps = hyp_map.get(v["id"], [])
        v["hypervisor_groups"] = [anon_index[h] for h in hyps]
        if show_names:
            v["hypervisors"] = hyps
    return vgpus


@app.route("/api/v3/domains/allowed/<kind>", methods=["GET"])
@app.route("/api/v3/domains/allowed/<kind>/<domain_id>", methods=["GET"])
@has_token
def api_v3_domains_allowed_hardware_reservables(payload, kind, domain_id=None):
    if kind == "reservables":
        # Admin UIs (webapp) may ask for real hypervisor names; the end-user
        # frontend (vue2) only gets anonymized group indices.
        show_names = request.args.get("hypervisor_names", "false").lower() == "true"
        if domain_id and ownsDomainId(payload, domain_id):
            domain_reservables_vgpus = _get_domain_reservables(domain_id)["vgpus"]
            vgpus = allowed.get_items_allowed(
                payload,
                "reservables_vgpus",
                query_pluck=["id", "name", "description", "model"],
                order="name",
                query_merge=False,
                extra_ids_allowed=domain_reservables_vgpus,
            )
        else:
            vgpus = allowed.get_items_allowed(
                payload,
                "reservables_vgpus",
                query_pluck=["id", "name", "description", "model"],
                order="name",
                query_merge=False,
            )
        return json.dumps({"vgpus": _attach_vgpu_hypervisor_groups(vgpus, show_names)})
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


# Will get allowed hardware quota max resources for different items
@app.route("/api/v3/quota/<kind>", methods=["GET"])
@app.route("/api/v3/quota/<kind>/<item_id>", methods=["GET"])
@is_admin_or_manager
def user_quota_max(payload, kind, item_id=None):
    if kind == "user":
        if not item_id:
            item_id = payload["user_id"]
        return (
            json.dumps(quotas.GetUserQuota(item_id)),
            200,
            {"Content-Type": "application/json"},
        )
    if kind == "category":
        if not item_id:
            item_id = payload["category_id"]
        return (
            json.dumps(quotas.GetCategoryQuota(item_id)),
            200,
            {"Content-Type": "application/json"},
        )
    if kind == "group":
        if not item_id:
            item_id = payload["group_id"]
        return (
            json.dumps(quotas.GetGroupQuota(item_id)),
            200,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/domain/info/<domain_id>", methods=["GET"])
@has_token
def api_v3_desktop_info(payload, domain_id):
    domain_def = get_document(
        "domains",
        domain_id,
        ["id", "kind", "name", "description", "image", "guest_properties"],
        invalidate=True,
    )
    domain = {
        **domain_def,
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


@app.route("/api/v3/desktop/owner/<desktop_id>/<user_id>", methods=["PUT"])
@is_admin_or_manager
def api_v3_desktop_change_owner(payload, desktop_id, user_id):
    ownsUserId(payload, user_id)
    ownsDomainId(payload, desktop_id)

    user = change_owner_desktop(user_id, desktop_id)
    return (
        json.dumps(user),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/template/owner/<template_id>/<user_id>", methods=["PUT"])
@is_admin_or_manager
def api_v3_template_change_owner(payload, template_id, user_id):
    ownsUserId(payload, user_id)
    ownsDomainId(payload, template_id)

    user = change_owner_template(user_id, template_id)
    return (
        json.dumps(user),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/media/owner/<media_id>/<user_id>", methods=["PUT"])
@is_admin_or_manager
def api_v3_media_change_owner(payload, media_id, user_id):
    ownsUserId(payload, user_id)
    ownsMediaId(payload, media_id)

    user = change_owner_media(user_id, media_id)
    return (
        json.dumps(user),
        200,
        {"Content-Type": "application/json"},
    )
