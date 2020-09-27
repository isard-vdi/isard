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

from ..libv2.api_desktops_persistent import ApiDesktopsPersistent
desktops = ApiDesktopsPersistent()

@app.route('/api/v2/persistent_desktop', methods=['POST'])
def api_v2_persistent_desktop_new():
    try:
        name = request.form.get('name', type = str)
        user_id = request.form.get('user_id', type = str)
        memory = request.form.get('memory', type = float)
        vcpus = request.form.get('vcpus', type = int)

        template_id = request.form.get('template_id', False, type = str)
        xml_id = request.form.get('xml_id', False, type = str)
        xml_definition = request.form.get('xml_definition', False, type = str)
        disk_size = request.form.get('disk_size', False, type = str)
        disk_path = request.form.get('disk_path', False, type = str)
        iso = request.form.get('iso', False, type = str)
        boot = request.form.get('template_id', 'disk', type = str)
    except Exception as e:
        return json.dumps({"code":8,"msg":"Incorrect access. exception: " + error }), 401, {'ContentType': 'application/json'}

    if user_id == None or name == None or vcpus == None or memory == None:
        log.error("Incorrect access parameters. Check your query.")
        return json.dumps({"code":8,"msg":"Incorrect access parameters. Check your query." }), 401, {'ContentType': 'application/json'}

    try:
        quotas.DesktopCreate(user_id)
    except QuotaUserNewDesktopExceeded:
        log.error("Quota for user "+user_id+" for creating another desktop is exceeded")
        return json.dumps({"code":11,"msg":"PersistentDestopNew user category quota CREATE exceeded"}), 507, {'ContentType': 'application/json'}
    except QuotaGroupNewDesktopExceeded:
        log.error("Quota for user "+user_id+" group for creating another desktop is exceeded")
        return json.dumps({"code":11,"msg":"PersistentDestopNew user category quota CREATE exceeded"}), 507, {'ContentType': 'application/json'}
    except QuotaCategoryNewDesktopExceeded:
        log.error("Quota for user "+user_id+" category for creating another desktop is exceeded")
        return json.dumps({"code":11,"msg":"PersistentDestopNew user category quota CREATE exceeded"}), 507, {'ContentType': 'application/json'}
    except Exception as e:
        error = traceback.format_exc()
        return json.dumps({"code":9,"msg":"PersistentDesktopNew quota check general exception: " + error }), 401, {'ContentType': 'application/json'}

    try:
        now=time.time()
        #desktop_id = app.lib.DesktopNewPersistent(name, user_id,memory,vcpus,xml_id=xml_id, disk_size=disk_size)

        desktop_id = desktops.DesktopNewPersistent(name, 
                                                    user_id,
                                                    memory,
                                                    vcpus,
                                                    from_template_id=template_id, 
                                                    xml_id=xml_id,
                                                    xml_definition=xml_definition,
                                                    disk_size=disk_size,
                                                    disk_path=disk_path,
                                                    iso=iso,
                                                    boot=boot)
        carbon.send({'create_and_start_time':str(round(time.time()-now,2))})
        return json.dumps({'id': desktop_id}), 200, {'ContentType': 'application/json'}
    except UserNotFound:
        log.error("Desktop for user "+user_id+" from template "+template_id+", user not found")
        return json.dumps({"code":1,"msg":"PersistentDestopNew user not found"}), 404, {'ContentType': 'application/json'}
    except TemplateNotFound:
        log.error("Desktop for user "+user_id+" from template "+template_id+" template not found.")
        return json.dumps({"code":2,"msg":"PersistentDesktopNew template not found"}), 404, {'ContentType': 'application/json'}
    except DesktopNotCreated:
        log.error("Desktop for user "+user_id+" from template "+template_id+" creation failed.")
        carbon.send({'create_and_start_time':'100'})
        return json.dumps({"code":1,"msg":"PersistentDestopNew not created"}), 404, {'ContentType': 'application/json'}
    ### Needs more!
    except Exception as e:
        error = traceback.format_exc()
        return json.dumps({"code":9,"msg":"PersistentDesktopNew general exception: " + error }), 401, {'ContentType': 'application/json'}


    #except DesktopStopTimeout:
    #    log.error("Desktop delete "+desktop_id+", desktop stop timeout")
    #    return json.dumps({"code":2,"msg":"Desktop delete stopping timeout"}), 404, {'ContentType': 'application/json'}
    #except DesktopStopFailed:
    #    log.error("Desktop delete "+desktop_id+", desktop stop failed")
    #    return json.dumps({"code":3,"msg":"Desktop delete stopping failed"}), 404, {'ContentType': 'application/json'}
    #except DesktopDeleteTimeout:
    #    log.error("Desktop delete "+desktop_id+", desktop delete timeout")
    #    return json.dumps({"code":4,"msg":"Desktop delete deleting timeout"}), 404, {'ContentType': 'application/json'}
