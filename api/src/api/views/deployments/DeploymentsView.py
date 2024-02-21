# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json

from api.libv2.api_desktop_events import deployment_delete
from api.libv2.api_desktops_common import ApiDesktopsCommon
from api.libv2.api_desktops_persistent import check_template_status
from api.libv2.api_hypervisors import check_storage_pool_availability
from api.libv2.deployments import api_deployments
from api.libv2.validators import _validate_item
from flask import request
from isardvdi_common.api_exceptions import Error

from api import app

from ..decorators import (
    allowedTemplateId,
    checkDuplicate,
    is_not_user,
    ownsDeploymentId,
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

    check_storage_pool_availability(data.get("category_id"))
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
    )
    return json.dumps({"id": data["id"]}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/deployments/<deployment_id>", methods=["DELETE"])
@app.route("/api/v3/deployments/<deployment_id>/<permanent>", methods=["DELETE"])
@is_not_user
def api_v3_deployments_delete(payload, deployment_id, permanent=False):
    ownsDeploymentId(payload, deployment_id)
    api_deployments.checkDesktopsStarted(deployment_id)
    deployment_delete(deployment_id, payload["user_id"], permanent)
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
    api_deployments.checkDesktopsStarted(deployment_id)
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
    api_deployments.edit_deployment(deployment_id, data)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/deployment/users/<deployment_id>", methods=["PUT"])
@is_not_user
def api_v3_deployment_edit_users(payload, deployment_id):
    ownsDeploymentId(payload, deployment_id)
    api_deployments.checkDesktopsStarted(deployment_id)
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
    api_deployments.edit_deployment_users(payload, deployment_id, data.get("allowed"))
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )
