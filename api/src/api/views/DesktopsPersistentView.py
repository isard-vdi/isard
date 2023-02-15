# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import traceback

from flask import request
from rethinkdb import RethinkDB

r = RethinkDB()

from api import app

from .._common.api_exceptions import Error
from ..libv2.api_logging import logs_domain_start_api, logs_domain_stop_api
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_allowed import ApiAllowed
from ..libv2.api_desktops_persistent import ApiDesktopsPersistent
from ..libv2.api_templates import ApiTemplates

templates = ApiTemplates()
desktops = ApiDesktopsPersistent()
allowed = ApiAllowed()

from ..libv2.api_scheduler import Scheduler
from ..libv2.validators import _validate_item, check_user_duplicated_domain_name
from .decorators import has_token, is_admin_or_manager, ownsDomainId

scheduler = Scheduler()


@app.route("/api/v3/desktops/new/check_quota", methods=["GET"])
@has_token
def api_v3_desktops_check_quota(payload):
    quotas.desktop_create(payload["user_id"])
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktop/start/<desktop_id>", methods=["GET"])
@has_token
def api_v3_desktop_start(payload, desktop_id):
    ownsDomainId(payload, desktop_id)
    user_id = desktops.UserDesktop(desktop_id)
    if payload["role_id"] != "admin":
        quotas.desktop_start(user_id, desktop_id)

    # So now we have checked if desktop exists and if we can create and/or start it
    desktop_id = desktops.Start(desktop_id)
    logs_domain_start_api(desktop_id, action_user=payload.get("user_id"))
    scheduler.add_desktop_timeouts(payload, desktop_id)

    return (
        json.dumps({"id": desktop_id}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktops/start", methods=["PUT"])
@has_token
def api_v3_desktops_start(payload):
    try:
        data = request.get_json(force=True)
        desktops_ids = data["desktops_ids"]
    except:
        Error(
            "bad_request",
            "Desktop start incorrect body data",
            traceback.format_exc(),
            "desktop_start_incorrect_body_data",
        )

    for desktop_id in desktops_ids:
        ownsDomainId(payload, desktop_id)
        user_id = desktops.UserDesktop(desktop_id)
        logs_domain_start_api(desktop_id, action_user=user_id)
        quotas.desktop_start(user_id, desktop_id)

    # So now we have checked if desktop exists and if we can create and/or start it
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktop/stop/<desktop_id>", methods=["GET"])
@has_token
def api_v3_desktop_stop(payload, desktop_id):
    ownsDomainId(payload, desktop_id)
    logs_domain_stop_api(desktop_id, action_user=payload.get("user_id"))
    return (
        json.dumps({"id": desktops.Stop(desktop_id)}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktops/stop", methods=["PUT"])
@has_token
def api_v3_desktops_stop(payload, desktop_id):
    try:
        data = request.get_json(force=True)
        desktops_ids = data["desktops_ids"]
    except:
        Error(
            "bad_request",
            "DesktopS start incorrect body data",
            traceback.format_exc(),
        )
    for desktop_id in desktops_ids:
        ownsDomainId(payload, desktop_id)
        logs_domain_stop_api(desktop_id, action_user=payload.get("user_id"))
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/persistent_desktop", methods=["POST"])
@has_token
def api_v3_persistent_desktop_new(payload):
    try:
        data = request.get_json(force=True)
    except:
        Error(
            "bad_request",
            "Desktop persistent add incorrect body data",
            traceback.format_exc(),
            description_code="desktop_incorrect_body_data",
        )

    data = _validate_item("desktop_from_template", data)
    template = templates.Get(data["template_id"])
    desktops.check_viewers(data["guest_properties"]["viewers"], data["hardware"])
    allowed.is_allowed(payload, template, "domains")
    quotas.desktop_create(payload["user_id"])
    check_user_duplicated_domain_name(
        data["name"],
        payload["user_id"],
    )

    desktops.NewFromTemplate(
        desktop_name=data["name"],
        desktop_description=data["description"],
        template_id=data["template_id"],
        user_id=payload["user_id"],
        new_data=data,
        image=data.get("image"),
        domain_id=data["id"],
    )
    return json.dumps({"id": data["id"]}), 200, {"Content-Type": "application/json"}


# Bulk desktops action
@app.route("/api/v3/persistent_desktop/bulk", methods=["POST"])
@is_admin_or_manager
def api_v3_persistent_desktop_bulk_new(payload):
    try:
        data = request.get_json(force=True)
    except:
        Error(
            "bad_request",
            "Desktop persistent add incorrect body data",
            traceback.format_exc(),
        )
    data = _validate_item("desktops_from_template", data)
    template = templates.Get(data["template_id"])
    allowed.is_allowed(payload, template, "domains")
    desktops_list = desktops.BulkDesktops(payload, data)

    return json.dumps(desktops_list), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/desktop/from/media", methods=["POST"])
@has_token
def api_v3_desktop_from_media(payload):
    try:
        data = request.get_json(force=True)
    except:
        Error(
            "bad_request",
            "Desktop persistent add incorrect body data",
            traceback.format_exc(),
        )
    data["user_id"] = payload["user_id"]
    data = _validate_item("desktop_from_media", data)
    check_user_duplicated_domain_name(
        data["name"],
        payload["user_id"],
    )
    quotas.desktop_create(payload["user_id"])
    desktop_id = desktops.NewFromMedia(payload, data)
    return json.dumps({"id": desktop_id}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/domain/<domain_id>", methods=["PUT"])
@has_token
def api_v3_domain_edit(payload, domain_id):
    try:
        data = request.get_json(force=True)
    except:
        raise Error(
            "bad_request",
            "Desktop edit incorrect body data",
            traceback.format_exc(),
            description_code="desktop_incorrect_body_data",
        )
    data["id"] = domain_id
    data = _validate_item("desktop_update", data)
    ownsDomainId(payload, domain_id)
    desktop = desktops.Get(desktop_id=domain_id)

    if not "server" in data and desktop.get("status") not in ["Failed", "Stopped"]:
        raise Error(
            "precondition_required",
            "Desktops only can be edited when stopped or failed",
            traceback.format_exc(),
        )

    if (
        desktop.get("server")
        and not "server" in data
        and desktop.get("status") != "Failed"
    ):
        raise Error(
            "precondition_required",
            "Servers can't be edited",
            traceback.format_exc(),
        )

    if data.get("name"):
        check_user_duplicated_domain_name(
            data["name"], desktop["user"], desktop.get("kind"), data["id"]
        )

    if data.get("forced_hyp") and payload["role_id"] != "admin":
        raise Error(
            "forbidden",
            "Only administrators can force an hypervisor",
            traceback.format_exc(),
        )

    desktops.check_viewers(data["guest_properties"]["viewers"], data["hardware"])
    admin_or_manager = True if payload["role_id"] in ["manager", "admin"] else False
    desktops.Update(domain_id, data, admin_or_manager)
    return (
        json.dumps(data),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktop/jumperurl/<desktop_id>", methods=["GET"])
@has_token
def api_v3_admin_viewer(payload, desktop_id):
    ownsDomainId(payload, desktop_id)
    data = desktops.JumperUrl(desktop_id)
    return (
        json.dumps(data),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktop/jumperurl_reset/<desktop_id>", methods=["PUT"])
@has_token
def admin_jumperurl_reset(payload, desktop_id):
    ownsDomainId(payload, desktop_id)
    try:
        data = request.get_json()
    except:
        raise Error("bad_request", "Bad body data", traceback.format_exc())
    response = desktops.JumperUrlReset(desktop_id, disabled=data.get("disabled"))
    return (
        json.dumps(response),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktop/<desktop_id>", methods=["DELETE"])
@has_token
def api_v3_desktop_delete(payload, desktop_id):
    ownsDomainId(payload, desktop_id)
    desktops.Delete(desktop_id)
    return json.dumps({}), 200, {"Content-Type": "application/json"}
