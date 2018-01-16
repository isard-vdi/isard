# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json

from flask import render_template, Response, request, redirect, url_for
from flask_login import login_required, login_user, logout_user, current_user

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
            log.error('Error registering client: '+str(e))
            return False
    return True
            
@app.route('/admin/updates/<kind>', methods=['GET'])
def admin_updates_json(kind):
        try:
            return json.dumps(u.getNewKind(kind,current_user.id))
        except Exception as e:
            print('exception on read updates: '+str(e))
            return json.dumps([])

@app.route('/admin/updates/update/<kind>', methods=['POST'])
def admin_updates_update(kind):
    if request.method == 'POST':
        data=u.getNewKind(kind,current_user.id)
        if kind == 'domains': 
            for d in data:
                d['id']='_'+current_user.id+'_'+d['id']
                d['percentage']=0
                d['status']='DownloadStarting'
                d.update(get_user_data())
                for disk in d['hardware']['disks']:
                    disk['file']=current_user.path+disk['file']
        elif kind == 'media':
            for d in data:
                if 'path' in d.keys():
                    d.update(get_user_data())
                    d['percentage']=0
                    d['status']='DownloadStarting'                    
                    d['path']=current_user.path+d['path']
        app.adminapi.insert_or_update_table_dict(kind,data)
    return json.dumps([])

def get_user_data():
    return {'category': current_user.category,
            'group': current_user.group,
            'user': current_user.id}
    
