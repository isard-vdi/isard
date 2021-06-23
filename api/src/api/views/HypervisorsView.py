# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
from api import app
import logging as log
import traceback

from uuid import uuid4
import time,json
import sys,os
from flask import request
from ..libv2.apiv2_exc import *
from ..libv2.quotas_exc import *

#from ..libv2.telegram import tsend
def tsend(txt):
    None
from ..libv2.carbon import Carbon
carbon = Carbon()

from ..libv2.quotas import Quotas
quotas = Quotas()

from ..libv2.api_hypervisors import ApiHypervisors
api_hypervisors = ApiHypervisors()

@app.route('/api/v2/guest_addr', methods=['POST'])
def api_v2_guest_addr():
    try:
        domain_id = request.form.get('id', type = str)
        ip = request.form.get('ip', type = str)
        mac = request.form.get('mac', type = str)
    except Exception as e:
        return json.dumps({"code":8,"msg":"Incorrect access. exception: " + error }), 500, {'Content-Type': 'application/json'}

    if domain_id == None or ip == None:
        log.error("Incorrect access parameters. Check your query.")
        return json.dumps({"code":8,"msg":"Incorrect access parameters. Check your query." }), 500, {'Content-Type': 'application/json'}

    try:
        api_hypervisors.update_guest_addr(domain_id,{'viewer':{'guest_ip':ip}})
        return json.dumps({}), 200, {'Content-Type': 'application/json'}
    except UpdateFailed:
        log.error("Update guest addr for domain "+domain_id+" with IP "+ip+", failed!")
        return json.dumps({"code":1,"msg":"DesktopNew user not found"}), 301, {'Content-Type': 'application/json'}
    except Exception as e:
        error = traceback.format_exc()
        log.error("Update guest addr general exception" + error)
        return json.dumps({"code":9,"msg":"Update guest addr general exception: " + error }), 500, {'Content-Type': 'application/json'}

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

@app.route('/api/v2/hypervisor', methods=['POST'])
@app.route('/api/v2/hypervisor/<hostname>', methods=['DELETE'])
def api_v2_hypervisor(hostname=False):
    if request.method == 'POST':
        try:
            hostname = request.form.get('hostname', type = str)
        except Exception as e:
            return json.dumps({"code":8,"msg":"Incorrect access. exception: " + error }), 500, {'Content-Type': 'application/json'}

        try:
            data=api_hypervisors.hyper(hostname)
            if not data['status']:
                return json.dumps({"code":1,"msg":"Failed hypervisor: " + data['msg'] }), 301, {'Content-Type': 'application/json'}
            return json.dumps(data['data']), 200, {'Content-Type': 'application/json'}
        except Exception as e:
            error = traceback.format_exc()
            log.error("Hypervisor general exception" + error)
            return json.dumps({"code":9,"msg":"Hypervisor general exception: " + error }), 500, {'Content-Type': 'application/json'}
    if request.method == 'DELETE':
        print(hostname)
        try:
            data=api_hypervisors.remove_hyper(hostname)
            if not data['status']:
                return json.dumps({"code":1,"msg":"Failed removing hypervisor: " + data['msg'] }), 301, {'Content-Type': 'application/json'}
            return json.dumps(data['data']), 200, {'Content-Type': 'application/json'}
        except Exception as e:
            error = traceback.format_exc()
            log.error("Hypervisor general exception" + error)
            return json.dumps({"code":9,"msg":"Hypervisor general exception: " + error }), 500, {'Content-Type': 'application/json'}


@app.route('/api/v2/hypervisor_vpn/<hyp_id>', methods=['GET'])
def api_v2_hypervisor_vpn(hyp_id):
    try:
        vpn=api_hypervisors.get_hypervisor_vpn(hyp_id)
        return json.dumps(vpn), 200, {'Content-Type': 'application/json'}
    except Exception as e:
        error = traceback.format_exc()
        log.error("ViewerCerts general exception" + error)
        return json.dumps({"code":9,"msg":"ViewerCerts general exception: " + error }), 500, {'Content-Type': 'application/json'}


@app.route('/api/v2/vlan', methods=['GET','POST'])
def api_v2_vlan():
    if request.method == 'POST':
        return json.dumps({"code":8,"msg":"Not implemented"}), 301, {'Content-Type': 'application/json'}

    if request.method == 'GET':
        try:
            vlans=api_hypervisors.get_vlans()
            return json.dumps(vlans), 200, {'Content-Type': 'application/json'}
        except Exception as e:
            error = traceback.format_exc()
            log.error("Vlans general exception" + error)
            return json.dumps({"code":9,"msg":"Vlans general exception: " + error }), 500, {'Content-Type': 'application/json'}

    log.error("Incorrect access parameters. Check your query.")
    return json.dumps({"code":8,"msg":"Incorrect access parameters. Check your query." }), 500, {'Content-Type': 'application/json'}
