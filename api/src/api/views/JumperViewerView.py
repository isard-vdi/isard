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

from flask import render_template, Response, request, redirect, url_for
#from ..libv2.telegram import tsend
def tsend(txt):
    None
from ..libv2.carbon import Carbon
carbon = Carbon()

from ..libv2.quotas import Quotas
quotas = Quotas()

from ..libv2.api_desktops_nonpersistent import ApiDesktopsNonPersistent
desktops = ApiDesktopsNonPersistent()

@app.route('/vw/<token>', methods=['GET'])
def api_v2_viewer(token):
    try:
        viewer=desktops.DesktopViewerFromToken(token)
        log.error(viewer)
        log.error(viewer)
        return render_template('jumper.html', data=(viewer))
        #return json.dumps(viewer), 200, {'ContentType': 'application/json'}
    except DesktopNotFound:
        log.error("Jumper viewer desktop not found")
        return json.dumps({"code":1,"msg":"Jumper viewer token not found"}), 404, {'ContentType': 'application/json'}
    except DesktopNotStarted:
        log.error("Jumper viewer desktop not started")
        return json.dumps({"code":2,"msg":"Jumper viewer desktop is not started"}), 404, {'ContentType': 'application/json'}
    except DesktopStartTimeout:
        log.error("Jumper viewer desktop start timeout.")
        carbon.send({'create_and_start_time':'100'})
        return json.dumps({"code":2,"msg":"Jumper viewer start timeout"}), 404, {'ContentType': 'application/json'}
    except NotAllowed:
        log.error("Jumper viewer desktop not allowed.")
        carbon.send({'create_and_start_time':'100'})
        return json.dumps({"code":2,"msg":"Jumper viewer start timeout"}), 404, {'ContentType': 'application/json'}

    except Exception as e:
        log.error("the error:"+str(e))
        error = traceback.format_exc()
        return json.dumps({"code":9,"msg":"JumperViewer general exception: " + error }), 401, {'ContentType': 'application/json'}
        
        