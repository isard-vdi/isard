# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import copy
import json
import traceback

from flask import request
from rethinkdb import RethinkDB

from ..libv2.helpers import _parse_desktop_booking

r = RethinkDB()

from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.api_hypervisors import check_storage_pool_availability
from ..libv2.api_logging import logs_domain_start_api, logs_domain_stop_api
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_admin import ApiAdmin
from ..libv2.api_allowed import ApiAllowed
from ..libv2.api_desktops_persistent import ApiDesktopsPersistent, check_template_status
from ..libv2.api_templates import ApiTemplates

templates = ApiTemplates()
desktops = ApiDesktopsPersistent()
allowed = ApiAllowed()
admin = ApiAdmin()

from ..libv2.api_scheduler import Scheduler
from ..libv2.validators import _validate_item, check_user_duplicated_domain_name
from .decorators import (
    has_token,
    is_admin_or_manager,
    is_admin_or_manager_or_advanced,
    ownsDeploymentDesktopId,
    ownsDomainId,
)

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

    if ownsDeploymentDesktopId(payload, desktop_id):
        desktop = quotas.deployment_desktop_start(payload["user_id"], desktop_id)
    else:
        desktop = quotas.desktop_start(user_id, desktop_id)
    desktop = _parse_desktop_booking(desktop)

    try:
        check_storage_pool_availability(payload.get("category_id"))
    except Error as e:
        raise Error(
            "precondition_required",
            e.error["description"],
            traceback.format_exc(),
            "hypervisors_not_available",
        )

    if desktop["needs_booking"]:
        try:
            desktops.check_current_plan(payload, desktop_id)
        except Error as e:
            err = e.error["description_code"]
            if err in [
                "current_plan_doesnt_match",
                "needs_deployment_booking",
            ] or payload["role_id"] not in ["admin", "manager"]:
                raise e

    # So now we have checked if desktop exists and if we can create and/or start it
    desktop_id = desktops.Start(desktop_id)
    logs_domain_start_api(
        desktop_id,
        action_user=payload.get("user_id"),
        user_request=request,
    )
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
        logs_domain_start_api(
            desktop_id,
            action_user=user_id,
            user_request=request,
        )
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


@app.route("/api/v3/desktop/updating/<desktop_id>", methods=["GET"])
@has_token
def api_v3_desktop_updaing(payload, desktop_id):
    ownsDomainId(payload, desktop_id)
    return (
        json.dumps({"id": desktops.Updating(desktop_id)}),
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
        raise Error(
            "bad_request",
            "Desktop persistent add incorrect body data",
            traceback.format_exc(),
            description_code="desktop_incorrect_body_data",
        )

    data = _validate_item("desktop_from_template", data)
    template = templates.Get(data["template_id"])

    data["description"] = data.get("description", template["description"])

    check_template_status(None, template)
    desktop = desktops.check_viewers(data, template)

    allowed.is_allowed(payload, template, "domains")
    quotas.desktop_create(payload["user_id"])
    check_user_duplicated_domain_name(
        desktop["name"],
        payload["user_id"],
    )
    check_storage_pool_availability(payload.get("category_id"))
    desktops.NewFromTemplate(
        desktop_name=desktop["name"],
        desktop_description=desktop["description"],
        template_id=desktop["template_id"],
        user_id=payload["user_id"],
        new_data=desktop,
        image=desktop.get("image"),
        domain_id=desktop["id"],
    )
    return json.dumps({"id": desktop["id"]}), 200, {"Content-Type": "application/json"}


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
    check_template_status(None, template)
    allowed.is_allowed(payload, template, "domains")
    check_storage_pool_availability(payload.get("category_id"))
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
@app.route("/api/v3/domain/bulk", methods=["PUT"])
@has_token
def api_v3_domain_edit(payload, domain_id=None):
    try:
        data = request.get_json(force=True)
    except:
        raise Error(
            "bad_request",
            "Desktop edit incorrect body data",
            traceback.format_exc(),
            description_code="desktop_incorrect_body_data",
        )

    admin_or_manager = payload["role_id"] in ["manager", "admin"]
    data = _validate_item("desktop_update", data)

    if (
        any(field in data for field in ["server", "favourite_hyp"])
        and not admin_or_manager
    ):
        raise Error(
            "forbidden",
            "Only administrators and managers can edit servers and favourite_hyp",
            traceback.format_exc(),
        )
    if "forced_hyp" in data and payload["role_id"] != "admin":
        raise Error(
            "forbidden",
            "Only administrators can force an hypervisor",
            traceback.format_exc(),
        )

    # Update an existing domain
    if domain_id:
        ownsDomainId(payload, domain_id)
        desktops.validate_desktop_update(data, domain_id)
        desktops.Update(domain_id, data, admin_or_manager)

    # Update multiple domains
    else:
        desktop_list = []
        for domain_id in data.get("ids"):
            ownsDomainId(payload, domain_id)
            new_data = copy.deepcopy(data)
            desktops.validate_desktop_update(new_data, domain_id)
            desktop_list.append(domain_id)

        desktops.Update(desktop_list, copy.deepcopy(data), admin_or_manager, bulk=True)

    return (
        json.dumps(data),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/domain/reservables/<domain_id>", methods=["PUT"])
@has_token
def api_v3_domain_edit_reservables(payload, domain_id):
    try:
        data = request.get_json(force=True)
    except:
        raise Error(
            "bad_request",
            "Desktop edit reservables incorrect body data",
            traceback.format_exc(),
            description_code="desktop_incorrect_body_data",
        )
    data = _validate_item("desktop_reservables_update", data)
    ownsDomainId(payload, domain_id)
    desktops.UpdateReservables(domain_id, reservables=data.get("reservables"))

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


@app.route("/api/v3/desktop/<desktop_id>/<permanent>", methods=["DELETE"])
@app.route("/api/v3/desktop/<desktop_id>", methods=["DELETE"])
@has_token
def api_v3_desktop_delete(payload, desktop_id, permanent=False):
    ownsDomainId(payload, desktop_id)
    desktops.Delete(desktop_id, payload["user_id"], permanent)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktop/update_storage_id/<desktop_id>", methods=["PUT"])
@has_token
def api_v3_desktop_update_storage_id(payload, desktop_id):
    ownsDomainId(payload, desktop_id)

    try:
        data = request.get_json(force=True)
    except:
        raise Error(
            "bad_request",
            "Desktop update storage id incorrect body data",
            traceback.format_exc(),
            description_code="desktop_incorrect_body_data",
        )
    if "storage_id" not in data:
        raise Error(
            "bad_request",
            "Desktop update storage id incorrect body data storage_id not found",
            traceback.format_exc(),
            description_code="desktop_incorrect_body_data",
        )

    desktops.update_storage(desktop_id, data["storage_id"])

    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


# @app.route("/api/v3/template/to/desktop", methods=["POST"])
# @is_admin_or_manager_or_advanced
# def api_v3_template_to_desktop(payload):
#     """
#     Endpoint to turn a template into a desktop

#     :param payload: Data from JWT
#     :type payload: dict
#     :return: JSON response
#     """
#     try:
#         data = request.get_json(force=True)
#     except:
#         raise Error(
#             "bad_request",
#             "Template to desktop incorrect body data",
#             traceback.format_exc(),
#             description_code="template_to_desktop_incorrect_body_data",
#         )

#     data = _validate_item("template_to_desktop", data)

#     tree = admin.GetTemplateTreeList(data["domain_id"], payload["user_id"])[0]
#     derivates = templates.check_children(payload, tree)

#     if derivates["pending"]:
#         raise Error(
#             "precondition_required",
#             "Template to desktop pending derivates",
#             traceback.format_exc(),
#             description_code="template_to_desktop_pending_derivates",
#         )
#     else:
#         child_ids = []

#         def get_children_ids(children):
#             for child in children:
#                 child_ids.append(child["id"])
#                 if child.get("children"):
#                     get_children_ids(child["children"])

#         get_children_ids(tree["children"])

#         data["children"] = child_ids

#     if data["name"] == None or data["domain_id"] == None:
#         raise Error(
#             "bad_request",
#             "Template to desktop bad body data",
#             traceback.format_exc(),
#             description_code="template_to_desktop_bad_body_data",
#         )

#     ownsDomainId(payload, data["domain_id"])
#     quotas.desktop_create(payload["user_id"], 1)
#     check_storage_pool_availability(payload.get("category_id"))

#     desktops.convertTemplateToDesktop(payload, data)

#     return json.dumps({}), 200, {"Content-Type": "application/json"}
