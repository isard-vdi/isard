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


from ..libv2.quotas import Quotas
quotas = Quotas()

from ..libv2.api_sundry import ApiSundry
api_sundry = ApiSundry()

from .decorators import has_token, is_admin

@app.route('/api/v3/guest_addr', methods=['POST'])
@is_admin
def api_v3_guest_addr(payload):
    try:
        domain_id = request.form.get('id', type = str)
        ip = request.form.get('ip', type = str)
        mac = request.form.get('mac', type = str)
    except Exception as e:
        return json.dumps({"code":8,"msg":"Incorrect access. exception: " + error }), 401, {'Content-Type': 'application/json'}

    if domain_id == None or ip == None:
        log.error("Incorrect access parameters. Check your query.")
        return json.dumps({"code":8,"msg":"Incorrect access parameters. Check your query." }), 401, {'Content-Type': 'application/json'}

    try:
        api_sundry.UpdateGuestAddr(domain_id,{'viewer':{'guest_ip':ip}})
        return json.dumps({}), 200, {'Content-Type': 'application/json'}
    except UpdateFailed:
        log.error("Desktop for user "+user_id+" from template "+template_id+", user not found")
        return json.dumps({"code":1,"msg":"DesktopNew user not found"}), 404, {'Content-Type': 'application/json'}
    except Exception as e:
        error = traceback.format_exc()
        log.error("GuestAddr general exception" + error)
        return json.dumps({"code":9,"msg":"GuestAddr general exception: " + error }), 401, {'Content-Type': 'application/json'}
