# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json
import time

from flask import render_template, Response, request, redirect, url_for, flash
from flask_login import login_required

from webapp import app
from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

import rethinkdb as r
from ...lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from .decorators import isAdmin

'''
HYPERVISORS
'''
@app.route('/isard-admin/admin/hypervisors', methods=['GET'])
@login_required
@isAdmin
def admin_hypervisors():
    # ~ hypers=app.adminapi.hypervisors_get()
    return render_template('admin/pages/hypervisors.html', title="Hypervisors", header="Hypervisors", nav="Hypervisors")

@app.route('/isard-admin/admin/hypervisors/json')
@app.route('/isard-admin/admin/hypervisors/json/<id>')
@login_required
@isAdmin
def admin_hypervisors_json(id=None):
    domain = app.adminapi.hypervisors_get(id)
    return json.dumps(domain), 200, {'Content-Type':'application/json'} 

@app.route('/isard-admin/admin/hypervisors_pools', methods=['GET','POST'])
@login_required
@isAdmin
def hypervisors_pools_get():
    res=True
    if request.method == 'POST':
        ca=request.form['viewer-certificate']
        pre_dict=request.form
        pre_dict.pop('viewer-certificate', None)
        create_dict=app.isardapi.f.unflatten_dict(request.form)
        create_dict['viewer']['certificate']=ca
        #check and parse name not done!
        create_dict['id']=create_dict['name']
        create_dict['interfaces']=[create_dict['interfaces']]
        if res == True:
            flash('Hypervisor pool '+create_dict['id']+' added to the system.','success')
            return render_template('admin/pages/hypervisors.html', title="Hypervisors", header="Hypervisors", nav="Hypervisors")
        else:
            flash('Could not create hypervisor pool. Maybe you have one with the same name?','danger')
            return render_template('pages/hypervisors.html',  nav="Hypervisors")
    return json.dumps(app.adminapi.hypervisors_pools_get(flat=False)), 200, {'Content-Type': 'application/json'}
        
    
