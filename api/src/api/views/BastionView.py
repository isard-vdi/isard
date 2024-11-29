import json
import os
import traceback

from flask import request
from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.api_allowed import ApiAllowed
from ..libv2.api_targets import ApiTargets
from ..libv2.validators import _validate_item, check_user_duplicated_domain_name
from .decorators import can_use_bastion, has_token, is_admin, ownsDomainId

#
#
#
#

alloweds = ApiAllowed()
targets = ApiTargets()


@app.route("/api/v3/desktop/bastion/<desktop_id>", methods=["GET"])
@has_token
def api_v3_get_desktop_bastion(payload, desktop_id):
    ownsDomainId(payload, desktop_id)
    if can_use_bastion(payload) == False:
        raise Error(
            "forbidden",
            "User can not use bastion",
            traceback.format_exc(),
        )

    try:
        target = targets.get_domain_target(desktop_id)
    except:
        target = targets.update_domain_target(desktop_id, {})
    return (
        json.dumps(target),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktop/bastion/<desktop_id>", methods=["PUT"])
@has_token
def api_v3_update_desktop_bastion(payload, desktop_id):
    ownsDomainId(payload, desktop_id)
    if can_use_bastion(payload) == False:
        raise Error(
            "forbidden",
            "User can not use bastion",
            traceback.format_exc(),
        )

    try:
        data = request.get_json(force=True)
    except:
        raise Error(
            "bad_request",
            "Desktop bastion update incorrect body data",
            traceback.format_exc(),
            description_code="desktop_bastion_incorrect_body_data",
        )
    data = _validate_item("bastion", data)
    targets.update_domain_target(desktop_id, data)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/bastions", methods=["GET"])
@has_token
def api_v3_get_bastions(payload):
    if can_use_bastion(payload) == False:
        raise Error(
            "forbidden",
            "User can not use bastion",
            traceback.format_exc(),
        )

    return (
        json.dumps(targets.get_user_targets(payload["user_id"])),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/bastion", methods=["GET"])
@is_admin
def api_v3_admin_bastion(payload):
    return (
        json.dumps(
            {
                "bastion_enabled": (
                    True
                    if (os.environ.get("BASTION_ENABLED", "false")).lower() == "true"
                    else False
                ),
                "bastion_ssh_port": os.environ.get(
                    "BASTION_SSH_PORT",
                    "2222",
                ),
            }
        ),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/admin/bastion/disallowed", methods=["DELETE"])
@is_admin
def admin_bastion_allowed_delete(payload):
    return (
        json.dumps(alloweds.remove_disallowed_bastion_targets()),
        200,
        {"Content-Type": "application/json"},
    )
