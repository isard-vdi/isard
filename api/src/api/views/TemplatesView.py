# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
from api import app
import logging as log

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

from ..libv2.api_users import ApiUsers
users = ApiUsers()

from ..libv2.api_desktops import ApiDesktops
desktops = ApiDesktops()

from ..libv2.api_desktops import ApiTemplates
templates = ApiTemplates()

@app.route('/api/v2/template', methods=['POST'])
def api_v2_template_new():
    try:
        name = request.form.get('name', type = str)
        user_id = request.form.get('user_id', type = str)
        desktop_id = request.form.get('desktop_id', type = str)
    except Exception as e:
        return json.dumps({"code":8,"msg":"Incorrect access. exception: " + str(e) }), 401, {'Content-Type': 'application/json'}

    if user_id == None or name == None or desktop_id == None:
        log.error("Incorrect access parameters. Check your query.")
        return json.dumps({"code":8,"msg":"Incorrect access parameters. Check your query." }), 401, {'Content-Type': 'application/json'}

    try:
        quotas.DesktopCreate(user_id)
    except QuotaUserNewDesktopExceeded:
        log.error("Quota for user "+user_id+" for creating another desktop is exceeded")
        return json.dumps({"code":11,"msg":"TemplateNew user category quota CREATE exceeded"}), 507, {'Content-Type': 'application/json'}
    except QuotaGroupNewDesktopExceeded:
        log.error("Quota for user "+user_id+" group for creating another desktop is exceeded")
        return json.dumps({"code":11,"msg":"TemplateNew user category quota CREATE exceeded"}), 507, {'Content-Type': 'application/json'}
    except QuotaCategoryNewDesktopExceeded:
        log.error("Quota for user "+user_id+" category for creating another desktop is exceeded")
        return json.dumps({"code":11,"msg":"TemplateNew user category quota CREATE exceeded"}), 507, {'Content-Type': 'application/json'}
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return json.dumps({"code":9,"msg":"TemplateNew quota check general exception: " + str(e) }), 401, {'Content-Type': 'application/json'}

    try:
        now=time.time()
        #desktop_id = app.lib.DesktopNewPersistent(name, user_id,memory,vcpus,xml_id=xml_id, disk_size=disk_size)
        template_id = templates.TemplateNew(name, user_id, desktop_id)
        carbon.send({'create_and_start_time':str(round(time.time()-now,2))})
        return json.dumps({'id': template_id}), 200, {'Content-Type': 'application/json'}
    except UserNotFound:
        log.error("Template for user "+user_id+" from desktop "+desktop_id+", user not found")
        return json.dumps({"code":1,"msg":"TemplateNew user not found"}), 404, {'Content-Type': 'application/json'}
    except TemplateNotFound:
        log.error("Template for user "+user_id+" from desktop "+desktop_id+" template not found.")
        return json.dumps({"code":2,"msg":"TemplateNew template not found"}), 404, {'Content-Type': 'application/json'}
    except DesktopNotCreated:
        log.error("Template for user "+user_id+" from desktop "+desktop_id+" creation failed.")
        carbon.send({'create_and_start_time':'100'})
        return json.dumps({"code":1,"msg":"TemplateNew not created"}), 404, {'Content-Type': 'application/json'}
    ### Needs more!
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(str(exc_type), str(fname), str(exc_tb.tb_lineno))
        return json.dumps({"code":9,"msg":"TemplateNew general exception: " + str(e) }), 401, {'Content-Type': 'application/json'}
