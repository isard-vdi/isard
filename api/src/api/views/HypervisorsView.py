# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import os
import traceback

from flask import request

#!flask/bin/python
# coding=utf-8
from api import app

from .._common.api_exceptions import Error
from .._common.storage_pool import DEFAULT_STORAGE_POOL_ID
from ..libv2 import api_hypervisors
from ..libv2.quotas import Quotas

quotas = Quotas()

from ..libv2.api_hypervisors import ApiHypervisors, get_hypervisors

api_hypervisors = ApiHypervisors()

from .decorators import is_admin, is_hyper


@app.route("/api/v3/hypervisors", methods=["GET"])
@app.route("/api/v3/hypervisors/<status>", methods=["GET"])
@is_admin
def api_v3_hypervisors(payload, status=None):
    if status and status not in ["Online", "Offline", "Error"]:
        raise Error(
            "bad_request",
            "Hypervisor status incorrect",
            traceback.format_exc(),
        )
    return (
        json.dumps(get_hypervisors(status)),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/hypervisor/vm/wg_addr", methods=["POST"])
@is_hyper
def api_v3_guest_addr():
    try:
        ip = request.form.get("ip", type=str)
        mac = request.form.get("mac", type=str)
    except:
        raise Error(
            "bad_request",
            "Hypervisor wg_addr bad bad data",
            traceback.format_exc(),
        )

    if mac == None or ip == None:
        raise Error(
            "bad_request",
            "Hypervisor wg_addr invalid body data",
            traceback.format_exc(),
        )

    domain_id = api_hypervisors.update_wg_address(mac, {"viewer": {"guest_ip": ip}})
    return (
        json.dumps({"domain_id": domain_id}),
        200,
        {"Content-Type": "application/json"},
    )


@app.route("/api/v3/hypervisor", methods=["POST"])
@app.route("/api/v3/hypervisor/<hyper_id>", methods=["DELETE", "PUT"])
@is_hyper
def api_v3_hypervisor(hyper_id=False):
    if request.method == "POST":
        try:
            hyper_id = request.form.get("hyper_id", type=str)
            hostname = request.form.get("hostname", type=str)
            user = request.form.get("user", default="root", type=str)
            port = request.form.get("port", default="2022", type=str)
            cap_disk = json.loads(
                request.form.get("cap_disk", default="true", type=str).lower()
            )
            cap_hyper = json.loads(
                request.form.get("cap_hyper", default="true", type=str).lower()
            )
            enabled = request.form.get("enabled", default=False, type=bool)
            browser_port = request.form.get("browser_port", default="443", type=str)
            spice_port = request.form.get("spice_port", default="80", type=str)
            isard_static_url = request.form.get(
                "isard_static_url", default=os.environ["DOMAIN"], type=str
            )
            isard_video_url = request.form.get(
                "isard_video_url", default=os.environ["DOMAIN"], type=str
            )
            isard_proxy_hyper_url = request.form.get(
                "isard_proxy_hyper_url", default="isard-hypervisor", type=str
            )
            isard_hyper_vpn_host = request.form.get(
                "isard_hyper_vpn_host", default=os.environ["DOMAIN"], type=str
            )
            description = request.form.get(
                "description", default="Added via api", type=str
            )
            only_forced = json.loads(
                request.form.get("only_forced", default="false", type=str).lower()
            )
            nvidia_enabled = (
                True if request.form.get("nvidia_enabled") == "True" else False
            )
            force_get_hyp_info = (
                True if request.form.get("force_get_hyp_info") == "True" else False
            )
            min_free_mem_gb = int(
                request.form.get("min_free_mem_gb", default="0", type=str)
            )
            storage_pools = request.form.get(
                "storage_pools", default=DEFAULT_STORAGE_POOL_ID, type=str
            ).split(",")
            buffering_hyper = json.loads(
                request.form.get("buffering_hyper", default="false", type=str).lower()
            )
            gpu_only = True if request.form.get("gpu_only") == "True" else False
        except:
            raise Error(
                "bad_request",
                "Hypervisor add bad data",
                traceback.format_exc(),
            )

        data = api_hypervisors.hyper(
            hyper_id,
            hostname,
            port=port,
            cap_disk=cap_disk,
            cap_hyper=cap_hyper,
            enabled=enabled,
            browser_port=browser_port,
            spice_port=spice_port,
            isard_static_url=isard_static_url,
            isard_video_url=isard_video_url,
            isard_proxy_hyper_url=isard_proxy_hyper_url,
            isard_hyper_vpn_host=isard_hyper_vpn_host,
            nvidia_enabled=nvidia_enabled,
            force_get_hyp_info=force_get_hyp_info,
            description=description,
            user=user,
            only_forced=only_forced,
            min_free_mem_gb=min_free_mem_gb,
            storage_pools=storage_pools,
            buffering_hyper=buffering_hyper,
            gpu_only=gpu_only,
        )
        if not data["status"]:
            raise Error("internal_server", "Failed hypervisor: " + data["msg"])
        return json.dumps(data["data"]), 200, {"Content-Type": "application/json"}

    if request.method == "DELETE":
        data = api_hypervisors.remove_hyper(hyper_id)
        if not data["status"]:
            raise Error(
                "bad_request",
                data["msg"],
                traceback.format_exc(),
            )
        return json.dumps(data["data"]), 200, {"Content-Type": "application/json"}

    if request.method == "PUT":
        log.warning("Enabling hypervisor: " + hyper_id)
        data = api_hypervisors.enable_hyper(hyper_id)
        if not data["status"]:
            raise Error(
                "bad_request",
                "Hypervisor update bad data",
                traceback.format_exc(),
            )
        return json.dumps(data["data"]), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/hypervisor/stop/<hyper_id>", methods=["PUT"])
@is_hyper
def api_v3_hypervisor_domains_stop(hyper_id):
    api_hypervisors.domains_stop(hyper_id)
    return (json.dumps({}), 200, {"Content-Type": "application/json"})


@app.route("/api/v3/hypervisor_vpn/<hyper_id>", methods=["GET"])
@is_hyper
def api_v3_hypervisor_vpn(hyper_id):
    vpn = api_hypervisors.get_hypervisor_vpn(hyper_id)
    return json.dumps(vpn), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/hypervisor/media_found", methods=["POST"])
@is_hyper
def api_v3_hypervisor_media_found():
    api_hypervisors.update_media_found(request.get_json(force=True))
    return json.dumps(True), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/hypervisor/disks_found", methods=["POST"])
@is_hyper
def api_v3_hypervisor_disks_found():
    api_hypervisors.update_disks_found(request.get_json(force=True))
    return json.dumps(True), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/hypervisor/media_delete", methods=["POST"])
@is_hyper
def api_v3_hypervisor_media_delete():
    api_hypervisors.delete_media(request.get_json(force=True))
    return json.dumps(True), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/hypervisors/gpus", methods=["PUT"])
@is_admin
def api_v3_hypervisors_gpus(payload):
    api_hypervisors.assign_gpus()
    return json.dumps(True), 200, {"Content-Type": "application/json"}


@app.route("/api/v3/hypervisor/status/<hyper_id>", methods=["GET"])
@is_admin
def api_v3_hypervisors_status(payload, hyper_id):
    status = api_hypervisors.get_hyper_status(hyper_id)
    return json.dumps(status), 200, {"Content-Type": "application/json"}
