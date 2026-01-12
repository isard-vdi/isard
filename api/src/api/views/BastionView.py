import json
import os
import traceback

from flask import request
from isardvdi_common.api_exceptions import Error

from api import app

from ..libv2.api_allowed import ApiAllowed
from ..libv2.api_targets import (
    ApiTargets,
    bastion_domain_verification_required,
    bastion_enabled_in_db,
    check_bastion_domain_dns,
    get_bastion_domain,
    update_bastion_config,
)
from ..libv2.validators import _validate_item
from .decorators import (
    bastion_enabled,
    can_use_bastion,
    can_use_bastion_individual_domains,
    checkDuplicateBastionDomains,
    has_token,
    is_admin,
    is_admin_or_manager,
    ownsDomainId,
)

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

    if not can_use_bastion_individual_domains(payload):
        data["domains"] = []

    targets.update_domain_target(desktop_id, data)
    return (
        json.dumps({}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/desktop/<desktop_id>/bastion/authorized_keys", methods=["PUT"])
@has_token
def api_v3_update_bastion_target_authorized_keys(payload, desktop_id):
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
        )

    if not data.get("authorized_keys"):
        raise Error(
            "bad_request",
            "Authorized keys are required",
            traceback.format_exc(),
        )

    target = targets.get_domain_target(desktop_id)
    target["ssh"]["authorized_keys"] = data["authorized_keys"]

    targets.update_domain_target(desktop_id, target)

    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/desktop/<desktop_id>/bastion/domains", methods=["PUT"])
@has_token
def api_v3_update_bastion_target_domains(payload, desktop_id):
    ownsDomainId(payload, desktop_id)
    if can_use_bastion(payload) == False:
        raise Error(
            "forbidden",
            "User can not use bastion",
            traceback.format_exc(),
        )

    if not can_use_bastion_individual_domains(payload):
        raise Error(
            "forbidden",
            "User can not use individual bastion domains",
            traceback.format_exc(),
        )

    try:
        data = request.get_json(force=True)
    except:
        raise Error(
            "bad_request",
            "Desktop bastion update incorrect body data",
            traceback.format_exc(),
        )

    if "domains" not in data:
        raise Error(
            "bad_request",
            "Domains list is required",
            traceback.format_exc(),
        )

    domains = data["domains"]
    if not isinstance(domains, list):
        raise Error(
            "bad_request",
            "Domains must be a list",
            traceback.format_exc(),
        )

    # Filter out empty/whitespace-only strings early
    domains = [d.strip() for d in domains if d and d.strip()]

    if len(domains) > 10:
        raise Error(
            "bad_request",
            "Maximum 10 domains allowed",
            traceback.format_exc(),
        )

    target = targets.get_domain_target(desktop_id)
    old_domains = set(target.get("domains", []))

    # Check duplicates for all domains (validates format before DNS)
    checkDuplicateBastionDomains(domains, target_id=target["id"])

    # DNS verification only for NEW domains (not already saved)
    if bastion_domain_verification_required():
        for domain in domains:
            if domain not in old_domains:
                check_bastion_domain_dns(
                    domain,
                    f"{target['id']}.{get_bastion_domain(payload['category_id'])}",
                    kind="cname",
                )

    targets.update_domain_target(desktop_id, {"domains": domains})

    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/desktop/<desktop_id>/bastion/domain/verify", methods=["POST"])
@has_token
def api_v3_verify_bastion_domain(payload, desktop_id):
    """Verify a single domain's DNS without saving. Returns success if CNAME is valid."""
    ownsDomainId(payload, desktop_id)
    if can_use_bastion(payload) == False:
        raise Error(
            "forbidden",
            "User can not use bastion",
            traceback.format_exc(),
        )

    if not can_use_bastion_individual_domains(payload):
        raise Error(
            "forbidden",
            "User can not use individual bastion domains",
            traceback.format_exc(),
        )

    try:
        data = request.get_json(force=True)
    except:
        raise Error(
            "bad_request",
            "Incorrect body data",
            traceback.format_exc(),
        )

    domain = data.get("domain", "").strip()
    if not domain:
        raise Error(
            "bad_request",
            "Domain is required",
            traceback.format_exc(),
        )

    target = targets.get_domain_target(desktop_id)

    # Check for duplicates (excluding current target)
    checkDuplicateBastionDomains([domain], target_id=target["id"])

    # Verify DNS
    if bastion_domain_verification_required():
        check_bastion_domain_dns(
            domain,
            f"{target['id']}.{get_bastion_domain(payload['category_id'])}",
            kind="cname",
        )

    return json.dumps({"verified": True}), 200, {"Content-Type": "application/json"}


# Backward compatibility endpoint for single domain
@app.route("/api/v3/desktop/<desktop_id>/bastion/domain", methods=["PUT"])
@has_token
def api_v3_update_bastion_target_domain_name(payload, desktop_id):
    ownsDomainId(payload, desktop_id)
    if can_use_bastion(payload) == False:
        raise Error(
            "forbidden",
            "User can not use bastion",
            traceback.format_exc(),
        )

    if not can_use_bastion_individual_domains(payload):
        raise Error(
            "forbidden",
            "User can not use individual bastion domains",
            traceback.format_exc(),
        )

    try:
        data = request.get_json(force=True)
    except:
        raise Error(
            "bad_request",
            "Desktop bastion update incorrect body data",
            traceback.format_exc(),
        )

    if "domain" not in data:
        raise Error(
            "bad_request",
            "Domain name is required",
            traceback.format_exc(),
        )

    # Convert single domain to array format
    domain = data["domain"]
    domains = [domain] if domain else []

    target = targets.get_domain_target(desktop_id)

    if domain and bastion_domain_verification_required():
        check_bastion_domain_dns(
            domain,
            f"{target['id']}.{get_bastion_domain(payload['category_id'])}",
            kind="cname",
        )

    checkDuplicateBastionDomains(domains, target_id=target["id"])

    targets.update_domain_target(desktop_id, {"domains": domains})

    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/bastion_targets", methods=["GET"])
@has_token
def api_v3_get_bastion_targets(payload):
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
    bastion_enabled_in_cfg = (
        True if os.environ.get("BASTION_ENABLED", "false").lower() == "true" else False
    )

    bastion_domain = get_bastion_domain()
    return (
        json.dumps(
            {
                "bastion_enabled": bastion_enabled(),
                "bastion_enabled_in_cfg": bastion_enabled_in_cfg,
                "bastion_enabled_in_db": bastion_enabled_in_db(),
                "bastion_domain": bastion_domain,
                "bastion_ssh_port": (
                    os.environ.get(
                        "BASTION_SSH_PORT",
                        os.environ.get("HTTPS_PORT", "443"),
                    )
                    if bastion_enabled()
                    else None
                ),
                "domain_verification_required": bastion_domain_verification_required(),
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


@app.route("/api/v3/admin/bastion/config", methods=["PUT"])
@is_admin
def admin_bastion_update_config(payload):
    try:
        data = request.get_json(force=True)
    except:
        raise Error(
            "bad_request",
            "Desktop bastion update incorrect body data",
            traceback.format_exc(),
            description_code="desktop_bastion_incorrect_body_data",
        )

    update_bastion_config(
        data["enabled"],
        data["bastion_domain"],
        data["domain_verification_required"],
    )
    return json.dumps({}), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/admin/bastion/config", methods=["GET"])
@is_admin_or_manager
def manager_bastion_config(payload):
    return (
        json.dumps(
            {"domain_verification_required": bastion_domain_verification_required()}
        ),
        200,
        {"Content-Type": "application/json"},
    )
