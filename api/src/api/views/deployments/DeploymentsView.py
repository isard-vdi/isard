# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import traceback

import gevent
from api.libv2.api_desktop_events import deployment_delete
from api.libv2.api_desktops_common import ApiDesktopsCommon
from api.libv2.api_desktops_persistent import (
    check_template_status,
    get_deployment_user_desktop,
)
from api.libv2.api_hypervisors import check_create_storage_pool_availability
from api.libv2.api_notify import notify_admins
from api.libv2.deployments import api_deployments
from api.libv2.validators import _validate_item
from flask import request
from isardvdi_common.api_exceptions import Error

from api import app, socketio

from ..decorators import (
    allowedTemplateId,
    checkDuplicate,
    has_token,
    is_admin_or_manager,
    is_not_user,
    ownsDeploymentId,
    ownsDomainId,
    ownsUserId,
)

common = ApiDesktopsCommon()
from api.libv2.quotas import Quotas

quotas = Quotas()


@app.route("/api/v3/deployment/<deployment_id>", methods=["GET"])
@is_not_user
def api_v3_deployment(payload, deployment_id):
    ownsDeploymentId(payload, deployment_id)
    deployment = api_deployments.get(deployment_id=deployment_id, desktops=True)
    return json.dumps(deployment), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/deployments", methods=["GET"])
@is_not_user
def api_v3_deployments(payload):
    deployments = api_deployments.lists(payload["user_id"])
    return json.dumps(deployments), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/deployments", methods=["POST"])
@is_not_user
def api_v3_deployments_new(payload):
    try:
        data = request.get_json(force=True)
    except:
        raise Error(
            "bad_request", "Could not decode body data", description_code="bad_request"
        )

    data = _validate_item("deployment", data)
    allowedTemplateId(payload, data["template_id"])
    check_template_status(data["template_id"])
    checkDuplicate("deployments", data["name"], user=payload["user_id"])

    check_create_storage_pool_availability(data.get("category_id"))
    api_deployments.new(
        payload,
        data["template_id"],
        data["name"],
        data["description"],
        data["desktop_name"],
        data["allowed"],
        data,
        visible=data["visible"],
        deployment_id=data["id"],
        user_permissions=data.get("user_permissions", []),
    )
    return json.dumps({"id": data["id"]}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/deployments/new/check_quota", methods=["GET", "POST"])
@is_not_user
def api_v3_deployments_check_quota(payload):
    users = []
    if request.method == "POST":
        try:
            data = request.get_json(force=True)
        except:
            raise Error(
                "bad_request",
                "Could not decode body data",
                description_code="bad_request",
            )
        allowed = data.get("allowed")
        users = api_deployments.get_selected_users(payload, allowed, "", "")

    quotas.deployment_create(users, payload["user_id"])
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/deployments/<deployment_id>", methods=["DELETE"])
@app.route("/api/v3/deployments/<deployment_id>/<permanent>", methods=["DELETE"])
@is_not_user
def api_v3_deployments_delete(payload, deployment_id, permanent=False):
    ownsDeploymentId(payload, deployment_id, check_co_owners=False)
    api_deployments.check_desktops_started(deployment_id)
    deployment_delete(deployment_id, payload["user_id"], permanent)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/deployments", methods=["DELETE"])
@is_not_user
def api_v3_deployments_delete_bulk(payload):
    deployment_ids = request.get_json()["ids"]
    permanent = request.get_json().get("permanent", False)
    exceptions = []

    for d_id in deployment_ids:
        try:
            ownsDeploymentId(payload, d_id, check_co_owners=False)
            api_deployments.check_desktops_started(d_id)
        except Error as e:
            exceptions.append(e.args[1])

    if exceptions:
        return (
            json.dumps({"exceptions": exceptions}),
            428,
            {"Content-Type": "application/json"},
        )

    def process_bulk_delete():
        try:
            for d_id in deployment_ids:
                deployment_delete(d_id, payload["user_id"], permanent)
            notify_admins(
                "deployment_action",
                {
                    "action": "delete",
                    "count": len(deployment_ids),
                    "status": "completed",
                },
            )

        except Error as e:
            app.logger.error(e)
            error_message = str(e)
            if isinstance(e.args, tuple) and len(e.args) > 1:
                app.logger.error(e.args[0])
                error_message = e.args[1]
            notify_admins(
                "deployment_action",
                {
                    "action": "delete",
                    "count": len(deployment_ids),
                    "msg": error_message,
                    "status": "failed",
                },
            )

        except Exception as e:
            app.logger.error(traceback.format_exc())
            notify_admins(
                "deployment_action",
                {
                    "action": "delete",
                    "count": len(deployment_ids),
                    "msg": "Something went wrong",
                    "status": "failed",
                },
            )

    gevent.spawn(process_bulk_delete)

    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/deployments/<deployment_id>", methods=["PUT"])
@is_not_user
def api_v3_deployments_recreate(payload, deployment_id):
    ownsDeploymentId(payload, deployment_id)
    api_deployments.recreate(payload, deployment_id)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/deployments/start/<deployment_id>", methods=["PUT"])
@is_not_user
def api_v3_deployments_start(payload, deployment_id):
    ownsDeploymentId(payload, deployment_id)
    api_deployments.start(deployment_id)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/deployments/stop/<deployment_id>", methods=["PUT"])
@is_not_user
def api_v3_deployments_stop(payload, deployment_id):
    ownsDeploymentId(payload, deployment_id)
    api_deployments.stop(deployment_id)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/deployments/visible/<deployment_id>", methods=["PUT"])
@is_not_user
def api_v3_deployments_viewer(payload, deployment_id):
    ownsDeploymentId(payload, deployment_id)
    data = request.get_json()
    api_deployments.visible(deployment_id, data.get("stop_started_domains"))

    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/deployments/domain/visible/<domain_id>", methods=["PUT"])
@is_not_user
def api_v3_deployments_domain_visible(payload, domain_id):
    ownsDomainId(payload, domain_id)
    api_deployments.user_visible(domain_id)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/deployments/directviewer_csv/<deployment_id>", methods=["GET"])
@is_not_user
def api_v3_deployments_directviewer_csv(payload, deployment_id):
    ownsDeploymentId(payload, deployment_id)
    reset_url = request.args.get("reset")
    if reset_url:
        api_deployments.jumper_url_reset(deployment_id)
    return (
        json.dumps(api_deployments.direct_viewer_csv(deployment_id)),
        200,
        {"Content-Type": "text/csv"},
    )


# Render deployment Hardware at deployment details' Hardware table
@app.route("/api/v3/deployment/hardware/<deployment_id>", methods=["GET"])
@is_not_user
def api_v3_deployment_hardware(payload, deployment_id):
    return (
        json.dumps(api_deployments.get_deployment_details_hardware(deployment_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/deployment/info/<deployment_id>", methods=["GET"])
@is_not_user
def api_v3_deployment_info(payload, deployment_id):
    ownsDeploymentId(payload, deployment_id)
    deployment = api_deployments.get_deployment_info(deployment_id)
    deployment = quotas.limit_user_hardware_allowed(payload, deployment)
    return (
        json.dumps(deployment),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/deployment/<deployment_id>", methods=["PUT"])
@is_not_user
def api_v3_deployment_edit(payload, deployment_id):
    ownsDeploymentId(payload, deployment_id)
    api_deployments.check_desktops_started(deployment_id)
    try:
        data = request.get_json(force=True)
    except:
        raise Error(
            "bad_request", "Could not decode body data", description_code="bad_request"
        )

    data = _validate_item("deployment_update", data)
    checkDuplicate(
        "deployments", data["name"], user=payload["user_id"], item_id=deployment_id
    )
    api_deployments.edit_deployment(payload, deployment_id, data)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/deployment/users/<deployment_id>", methods=["PUT"])
@is_not_user
def api_v3_deployment_edit_users(payload, deployment_id):
    ownsDeploymentId(payload, deployment_id)
    api_deployments.check_desktops_started(deployment_id)
    try:
        data = request.get_json(force=True)
        if data.get("allowed").get("categories"):
            data.get("allowed").pop("categories")
        if data.get("allowed").get("roles"):
            data.get("allowed").pop("roles")
    except:
        raise Error(
            "bad_request", "Could not decode body data", description_code="bad_request"
        )

    data = _validate_item("allowed", data)

    users = api_deployments.get_selected_users(payload, data["allowed"], "", "")
    quotas.deployment_update(users, payload["user_id"])

    api_deployments.edit_deployment_users(payload, deployment_id, data.get("allowed"))
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/deployment/co-owners/<deployment_id>", methods=["GET"])
@is_not_user
def api_v3_deployment_get_co_owners(payload, deployment_id):
    ownsDeploymentId(payload, deployment_id)
    co_owners = api_deployments.get_co_owners(deployment_id)

    return (
        json.dumps(co_owners),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/deployment/co-owners/<deployment_id>", methods=["PUT"])
@is_not_user
def api_v3_deployment_update_co_owners(payload, deployment_id):
    ownsDeploymentId(payload, deployment_id, check_co_owners=False)
    try:
        data = request.get_json(force=True)
    except:
        raise Error(
            "bad_request", "Could not decode body data", description_code="bad_request"
        )
    data = _validate_item("co_owners", data)

    api_deployments.update_co_owners(deployment_id, data.get("co_owners"))
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/deployment/owner/<deployment_id>/<user_id>", methods=["PUT"])
@is_admin_or_manager
def api_v3_deployment_change_owner(payload, deployment_id, user_id=False):
    ownsUserId(payload, user_id)
    ownsDeploymentId(payload, deployment_id, check_co_owners=False)

    api_deployments.change_owner_deployment(payload, deployment_id, user_id)
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/deployment/permissions/<deployment_id>", methods=["GET"])
@is_not_user
def api_v3_get_deployment_permissions(payload, deployment_id):
    ownsDeploymentId(payload, deployment_id)
    return (
        json.dumps(api_deployments.get_deployment_permissions(deployment_id)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/user/<user_id>/deployment/<deployment_id>", methods=["GET"])
@has_token
def api_v3_get_user_deployment_desktop(payload, user_id, deployment_id):
    desktop = get_deployment_user_desktop(user_id, deployment_id)
    if not desktop:
        raise Error(
            "not_found",
            "Desktop not found",
            description_code="desktop_not_found",
        )
    ownsDomainId(payload, desktop["id"])
    return json.dumps(desktop), 200, {"Content-Type": "application/json"}
