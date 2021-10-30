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

from ..libv2.apiv2_exc import *
from ..libv2.quotas import Quotas
from ..libv2.quotas_exc import *

quotas = Quotas()

from ..libv2.api_hypervisors import ApiHypervisors

api_hypervisors = ApiHypervisors()

from .decorators import is_hyper

# @app.route('/api/v3/hypervisor/vm/guest_addr', methods=['POST'])
# @is_hyper
# def api_v3_guest_addr():
#     try:
#         domain_id = request.form.get('id', type = str)
#         ip = request.form.get('ip', type = str)
#         mac = request.form.get('mac', type = str)
#     except:
#         error = traceback.format_exc()
#         log.error("Guest addr incorrect access" + error)
#         return json.dumps({"code":8,"msg":"Incorrect access. exception: " + error }), 500, {'Content-Type': 'application/json'}

#     if domain_id == None or ip == None:
#         log.warning("Incorrect access parameters. Check your query.")
#         return json.dumps({"code":8,"msg":"Incorrect access parameters. Check your query." }), 500, {'Content-Type': 'application/json'}

#     try:
#         api_hypervisors.update_guest_addr(domain_id,{'viewer':{'guest_ip':ip}})
#         return json.dumps({"domain":domain_id,"guest_ip":ip,"action":"updated"}), 200, {'Content-Type': 'application/json'}
#     except UpdateFailed:
#         log.error("Update guest addr for domain "+domain_id+" with IP "+ip+", failed!")
#         return json.dumps({"code":1,"msg":"UpdateGuestAddr update failed"}), 301, {'Content-Type': 'application/json'}
#     except Exception as e:
#         error = traceback.format_exc()
#         log.error("Update guest addr general exception" + error)
#         return json.dumps({"code":9,"msg":"Update guest addr general exception: " + error }), 500, {'Content-Type': 'application/json'}


@app.route("/api/v3/hypervisor/vm/wg_addr", methods=["POST"])
@is_hyper
def api_v3_guest_addr():
    try:
        ip = request.form.get("ip", type=str)
        mac = request.form.get("mac", type=str)
    except:
        error = traceback.format_exc()
        log.error("Guest addr incorrect access" + error)
        return (
            json.dumps({"code": 8, "msg": "Incorrect access. exception: " + error}),
            500,
            {"Content-Type": "application/json"},
        )

    if mac == None or ip == None:
        log.warning("Incorrect access parameters. Check your query.")
        return (
            json.dumps(
                {"code": 8, "msg": "Incorrect access parameters. Check your query."}
            ),
            500,
            {"Content-Type": "application/json"},
        )

    try:
        domain_id = api_hypervisors.update_wg_address(mac, {"viewer": {"guest_ip": ip}})
        if domain_id:
            return (
                json.dumps({"domain_id": domain_id}),
                200,
                {"Content-Type": "application/json"},
            )
        else:
            log.error(
                "Update guest addr for mac " + mac + " with IP " + ip + ", failed!"
            )
            return (
                json.dumps({"code": 1, "msg": "UpdateWgAddr update failed"}),
                301,
                {"Content-Type": "application/json"},
            )
    except Exception as e:
        error = traceback.format_exc()
        log.error("Update guest addr general exception" + error)
        return (
            json.dumps(
                {"code": 9, "msg": "Update guest addr general exception: " + error}
            ),
            500,
            {"Content-Type": "application/json"},
        )


# Not directly used anymore
# @app.route('/api/v2/hypervisor_certs', methods=['GET'])
# def api_v2_hypervisor_certs():
#     try:
#         certs=api_hypervisors.get_hypervisors_certs()
#         return json.dumps(certs), 200, {'Content-Type': 'application/json'}
#     except Exception as e:
#         error = traceback.format_exc()
#         log.error("ViewerCerts general exception" + error)
#         return json.dumps({"code":9,"msg":"ViewerCerts general exception: " + error }), 500, {'Content-Type': 'application/json'}


@app.route("/api/v3/hypervisor", methods=["POST"])
@app.route("/api/v3/hypervisor/<hyper_id>", methods=["DELETE", "PUT"])
@is_hyper
def api_v3_hypervisor(hyper_id=False):
    if request.method == "POST":
        try:
            hyper_id = request.form.get("hyper_id", type=str)
            hostname = request.form.get("hostname", type=str)
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

        except Exception as e:
            error = traceback.format_exc()
            return (
                json.dumps({"code": 8, "msg": "Incorrect access. exception: " + error}),
                500,
                {"Content-Type": "application/json"},
            )

        try:
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
            )
            if not data["status"]:
                log.warning(data)
                return (
                    json.dumps({"code": 1, "msg": "Failed hypervisor: " + data["msg"]}),
                    301,
                    {"Content-Type": "application/json"},
                )
            return json.dumps(data["data"]), 200, {"Content-Type": "application/json"}
        except Exception as e:
            error = traceback.format_exc()
            log.error("Hypervisor general exception" + error)
            return (
                json.dumps(
                    {"code": 9, "msg": "Hypervisor general exception: " + error}
                ),
                500,
                {"Content-Type": "application/json"},
            )
    if request.method == "DELETE":
        try:
            data = api_hypervisors.remove_hyper(hyper_id)
            if not data["status"]:
                log.warning(data)
                return (
                    json.dumps(
                        {"code": 1, "msg": "Failed removing hypervisor: " + data["msg"]}
                    ),
                    301,
                    {"Content-Type": "application/json"},
                )
            return json.dumps(data["data"]), 200, {"Content-Type": "application/json"}
        except Exception as e:
            error = traceback.format_exc()
            log.error("Hypervisor general exception" + error)
            return (
                json.dumps(
                    {"code": 9, "msg": "Hypervisor general exception: " + error}
                ),
                500,
                {"Content-Type": "application/json"},
            )
    if request.method == "PUT":
        try:
            log.warning("Enabling hypervisor: " + hyper_id)
            data = api_hypervisors.enable_hyper(hyper_id)
            if not data["status"]:
                log.warning(data)
                return (
                    json.dumps(
                        {"code": 1, "msg": "Failed updating hypervisor: " + data["msg"]}
                    ),
                    301,
                    {"Content-Type": "application/json"},
                )
            return json.dumps(data["data"]), 200, {"Content-Type": "application/json"}
        except Exception as e:
            error = traceback.format_exc()
            log.error("Hypervisor general exception" + error)
            return (
                json.dumps(
                    {"code": 9, "msg": "Hypervisor general exception: " + error}
                ),
                500,
                {"Content-Type": "application/json"},
            )


@app.route("/api/v3/hypervisor_vpn/<hyper_id>", methods=["GET"])
@is_hyper
def api_v3_hypervisor_vpn(hyper_id):
    try:
        vpn = api_hypervisors.get_hypervisor_vpn(hyper_id)
        return json.dumps(vpn), 200, {"Content-Type": "application/json"}
    except Exception as e:
        error = traceback.format_exc()
        log.error("HypervisorVpn general exception" + error)
        return (
            json.dumps({"code": 9, "msg": "HypervisorVpn general exception: " + error}),
            500,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/hypervisor/media_found", methods=["POST"])
@is_hyper
def api_v3_hypervisor_media_found():
    try:
        api_hypervisors.update_media_found(request.get_json(force=True))
        return json.dumps(True), 200, {"Content-Type": "application/json"}
    except:
        error = traceback.format_exc()
        log.error("HypervisorMediaFound general exception" + error)
        return (
            json.dumps(
                {"code": 9, "msg": "HypervisorMediaFound general exception: " + error}
            ),
            500,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/hypervisor/disks_found", methods=["POST"])
@is_hyper
def api_v3_hypervisor_disks_found():
    try:
        api_hypervisors.update_disks_found(request.get_json(force=True))
        return json.dumps(True), 200, {"Content-Type": "application/json"}
    except:
        error = traceback.format_exc()
        log.error("HypervisorDisksFound general exception" + error)
        return (
            json.dumps(
                {"code": 9, "msg": "HypervisorDisksFound general exception: " + error}
            ),
            500,
            {"Content-Type": "application/json"},
        )


@app.route("/api/v3/hypervisor/media_delete", methods=["POST"])
@is_hyper
def api_v3_hypervisor_media_delete():
    try:
        api_hypervisors.delete_media(request.get_json(force=True))
        return json.dumps(True), 200, {"Content-Type": "application/json"}
    except:
        error = traceback.format_exc()
        log.error("HypervisorMediaFound general exception" + error)
        return (
            json.dumps(
                {"code": 9, "msg": "HypervisorMediaFound general exception: " + error}
            ),
            500,
            {"Content-Type": "application/json"},
        )


# @app.route('/api/v3/hypervisor/groups_found', methods=['POST'])
# @is_hyper
# def api_v3_hypervisor_groups_found():
#     try:
#         api_hypervisors.update_disks_found('groups',request.get_json(force=True))
#         return json.dumps(True), 200, {'Content-Type': 'application/json'}
#     except Exception as e:
#         error = traceback.format_exc()
#         log.error("HypervisorMediaFound general exception" + error)
#         return json.dumps({"code":9,"msg":"HypervisorMediaFound general exception: " + error }), 500, {'Content-Type': 'application/json'}


# @app.route('/api/v3/vlans', methods=['GET','POST'])
# @is_hyper
# def api_v3_vlans():
#     if request.method == 'POST':
#         try:
#             vlans = request.get_json(force=True)
#         except Exception as e:
#             error = traceback.format_exc()
#             return json.dumps({"code":8,"msg":"Incorrect access. exception: " + error }), 500, {'Content-Type': 'application/json'}

#         try:
#             api_hypervisors.add_vlans(vlans)
#             return json.dumps({}), 200, {'Content-Type': 'application/json'}
#         except Exception as e:
#             error = traceback.format_exc()
#             log.error("Vlans add general exception" + error)
#             return json.dumps({"code":9,"msg":"Vlans add general exception: " + error }), 500, {'Content-Type': 'application/json'}

#     if request.method == 'GET':
#         try:
#             vlans=api_hypervisors.get_vlans()
#             return json.dumps(vlans), 200, {'Content-Type': 'application/json'}
#         except Exception as e:
#             error = traceback.format_exc()
#             log.error("Vlans general exception" + error)
#             return json.dumps({"code":9,"msg":"Vlans general exception: " + error }), 500, {'Content-Type': 'application/json'}

#     log.error("Incorrect access parameters. Check your query.")
#     return json.dumps({"code":8,"msg":"Incorrect access parameters. Check your query." }), 500, {'Content-Type': 'application/json'}
