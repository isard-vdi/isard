# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging as log
import os
import sys
import time
import traceback
from uuid import uuid4

from flask import request

#!flask/bin/python
# coding=utf-8
from api import app

from ..libv2 import api_hypervisors
from ..libv2.api_exceptions import Error
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
            "bad_request", "Hypervisor status incorrect", traceback.format_stack()
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
            "bad_request", "Hypervisor wg_addr bad bad data", traceback.format_stack()
        )

    if mac == None or ip == None:
        raise Error(
            "bad_request",
            "Hypervisor wg_addr invalid body data",
            traceback.format_stack(),
        )

    domain_id = api_hypervisors.update_wg_address(mac, {"viewer": {"guest_ip": ip}})
    return (
        json.dumps({"domain_id": domain_id}),
        200,
        {"Content-Type": "application/json"},
    )


# Not directly used anymore
# @app.route('/api/v2/hypervisor_certs', methods=['GET'])
# def api_v2_hypervisor_certs():
#     try:
#         certs=api_hypervisors.get_hypervisors_certs()
#         return json.dumps(certs), 200, {'Content-Type': 'application/json'}
#     except Exception as e:
#         error = traceback.format_stack()
#         log.error("ViewerCerts general exception" + error)
#         return json.dumps({"error": "undefined_error","msg":"ViewerCerts general exception: " + error }), 500, {'Content-Type': 'application/json'}


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
            cap_hyper = request.form.get("cap_hyper", default=True, type=bool)
            cap_disk = request.form.get("cap_disk", default=True, type=bool)
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

        except:
            raise Error(
                "bad_request", "Hypervisor add bad data", traceback.format_stack()
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
            description=description,
            user=user,
            only_forced=only_forced,
        )
        if not data["status"]:
            raise Error("internal_server", "Failed hypervisor: " + data["msg"])
        return json.dumps(data["data"]), 200, {"Content-Type": "application/json"}

    if request.method == "DELETE":
        data = api_hypervisors.remove_hyper(hyper_id)
        if not data["status"]:
            raise Error(
                "bad_request",
                "Hypervisor delete add bad data",
                traceback.format_stack(),
            )
        return json.dumps(data["data"]), 200, {"Content-Type": "application/json"}

    if request.method == "PUT":
        log.warning("Enabling hypervisor: " + hyper_id)
        data = api_hypervisors.enable_hyper(hyper_id)
        if not data["status"]:
            raise Error(
                "bad_request", "Hypervisor update bad data", traceback.format_stack()
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


# @app.route('/api/v3/hypervisor/groups_found', methods=['POST'])
# @is_hyper
# def api_v3_hypervisor_groups_found():
#     try:
#         api_hypervisors.update_disks_found('groups',request.get_json(force=True))
#         return json.dumps(True), 200, {'Content-Type': 'application/json'}
#     except Exception as e:
#         error = traceback.format_stack()
#         log.error("HypervisorMediaFound general exception" + error)
#         return json.dumps({"error": "undefined_error","msg":"HypervisorMediaFound general exception: " + error }), 500, {'Content-Type': 'application/json'}


# @app.route('/api/v3/vlans', methods=['GET','POST'])
# @is_hyper
# def api_v3_vlans():
#     if request.method == 'POST':
#         try:
#             vlans = request.get_json(force=True)
#         except Exception as e:
#             error = traceback.format_stack()
#             return json.dumps({"error": "undefined_error","msg":"Incorrect access. exception: " + error }), 500, {'Content-Type': 'application/json'}

#         try:
#             api_hypervisors.add_vlans(vlans)
#             return json.dumps({}), 200, {'Content-Type': 'application/json'}
#         except Exception as e:
#             error = traceback.format_stack()
#             log.error("Vlans add general exception" + error)
#             return json.dumps({"error": "undefined_error","msg":"Vlans add general exception: " + error }), 500, {'Content-Type': 'application/json'}

#     if request.method == 'GET':
#         try:
#             vlans=api_hypervisors.get_vlans()
#             return json.dumps(vlans), 200, {'Content-Type': 'application/json'}
#         except Exception as e:
#             error = traceback.format_stack()
#             log.error("Vlans general exception" + error)
#             return json.dumps({"error": "undefined_error","msg":"Vlans general exception: " + error }), 500, {'Content-Type': 'application/json'}

#     log.error("Incorrect access parameters. Check your query.")
#     return json.dumps({"error": "undefined_error","msg":"Incorrect access parameters. Check your query." }), 500, {'Content-Type': 'application/json'}
