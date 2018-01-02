# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json

from flask import render_template, Response, request, redirect, url_for
from flask_login import login_required

from webapp import app
from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

import rethinkdb as r
from ...lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from ...lib.isardUpdates import Updates
u=Updates()
from .decorators import isAdmin

@app.route('/admin/updates', methods=['GET'])
def admin_updates():
    return render_template('admin/pages/updates.html', nav="Updates", )

@app.route('/admin/updates_register', methods=['POST'])
def admin_updates_register():
    if request.method == 'POST':
        try:
            if not u.isRegistered():
                u.register()
        except Exception as e:
            return False
    return True
            
@app.route('/admin/updates/<kind>', methods=['GET'])
def admin_updates_json(kind):
    #~ if request.method == 'POST':
        try:
            import pprint
            if kind == 'domains': pprint.pprint(u.getNewKind('domains'))
            return json.dumps(u.getNewKind(kind))
        except Exception as e:
            print('exception on read updates: '+str(e))
            return json.dumps([])

@app.route('/admin/updates/update/<kind>', methods=['POST'])
def admin_updates_update(kind):
    if request.method == 'POST':
        app.adminapi.insert_or_update_table_dict(kind,u.getNewKind(kind))
    return json.dumps([])
    
    
