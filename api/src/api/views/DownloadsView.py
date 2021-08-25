# Copyright 2017 the Isard-vdi project
# License: AGPLv3

#!flask/bin/python3
# coding=utf-8

from api import app
from ..libv2.log import log
import traceback

from uuid import uuid4
import time,json
import sys,os
from flask import request, jsonify
from ..libv2.apiv2_exc import *
from ..libv2.quotas_exc import *

from ..libv2.quotas import Quotas
quotas = Quotas()

from ..libv2.api_users import ApiUsers, check_category_domain
users = ApiUsers()

from ..libv2.api_downloads import Downloads


from .decorators import is_admin_user

'''
ADMIN/MANAGER jwt endpoints
'''
@app.route('/api/v3/admin/downloads/desktops', methods=['GET'])
@is_admin_user
def api_v3_admin_downloads_desktops(payload):
    downloads = Downloads()
    return json.dumps(downloads.getNewKind('domains',payload['user_id'])), 200, {'Content-Type': 'application/json'}

@app.route('/api/v3/admin/downloads/desktop/<desktop_id>', methods=['POST'])
@is_admin_user
def api_v3_admin_downloads_desktops_download(desktop_id,payload):
    downloads = Downloads()
    res = downloads.download_desktop(desktop_id,payload['user_id'])
    if not res:
        json.dumps({'code':8,'description':'Could not download desktop'}), 401, {'Content-Type': 'application/json'}
    return json.dumps({}), 200, {'Content-Type': 'application/json'}
