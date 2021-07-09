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

from flask import render_template, Response, request, redirect, url_for, send_file, send_from_directory

from ..libv2.quotas import Quotas
quotas = Quotas()

from ..libv2.api_desktops_common import ApiDesktopsCommon
common = ApiDesktopsCommon()

@app.route('/vw/img/<img>', methods=['GET'])
def api_v3_img(img):
    return send_from_directory('templates/',img)

@app.route('/vw/<token>', methods=['GET'])
def api_v3_viewer(token):
    try:
        viewers=common.DesktopViewerFromToken(token)
        protocol = request.args.get('protocol', default = False)
        return render_template('jumper.html', vmName=viewers['vmName'], vmDescription=viewers['vmDescription'], viewers=json.dumps(viewers))
        #return render_template('jumper.html', data='')
    except DesktopNotFound:
        log.error("Jumper viewer desktop not found")
        return render_template('error.html', error='Incorrect access')
        #return json.dumps({"code":1,"msg":"Jumper viewer token not found"}), 404, {'Content-Type': 'application/json'}
    except DesktopNotStarted:
        log.error("Jumper viewer desktop not started")
        return render_template('error.html', error='Desktop could not be started. Try again in a while...')
        #return json.dumps({"code":2,"msg":"Jumper viewer desktop is not started"}), 404, {'Content-Type': 'application/json'}
    except DesktopActionTimeout:
        log.error("Jumper viewer desktop start timeout.")
        return render_template('error.html', error='Desktop start timed out. Try again in a while...')
        #return json.dumps({"code":2,"msg":"Jumper viewer start timeout"}), 404, {'Content-Type': 'application/json'}
    except Exception as e:
        error = traceback.format_exc()
        log.error("Jumper viewer general exception: "+error)
        return render_template('error.html', error='Incorrect access.')
        #return json.dumps({"code":9,"msg":"JumperViewer general exception: " + error }), 401, {'Content-Type': 'application/json'}
        
        
