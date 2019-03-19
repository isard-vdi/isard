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
@app.route('/admin/hypervisors', methods=['GET'])
@login_required
@isAdmin
def admin_hypervisors():
    # ~ hypers=app.adminapi.hypervisors_get()
    return render_template('admin/pages/hypervisors.html', title="Hypervisors", header="Hypervisors", nav="Hypervisors")

@app.route('/admin/hypervisors/json')
@app.route('/admin/hypervisors/json/<id>')
@login_required
@isAdmin
def admin_hypervisors_json(id=None):
    domain = app.adminapi.hypervisors_get(id)
    return json.dumps(domain), 200, {'ContentType':'application/json'} 

@app.route('/admin/hypervisors_pools', methods=['GET','POST'])
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
        if res is True:
            flash('Hypervisor pool '+create_dict['id']+' added to the system.','success')
            return render_template('admin/pages/hypervisors.html', title="Hypervisors", header="Hypervisors", nav="Hypervisors")
        else:
            flash('Could not create hypervisor pool. Maybe you have one with the same name?','danger')
            return render_template('pages/hypervisors.html',  nav="Hypervisors")
    return json.dumps(app.adminapi.hypervisors_pools_get(flat=False)), 200, {'ContentType': 'application/json'}
        
# ~ @app.route('/admin/hypervisors_update', methods=['POST', 'GET'])
# ~ @login_required
# ~ @isAdmin
# ~ def admin_hypervisors_update():
    # ~ if request.method == 'POST':
        # ~ try:
            # ~ args = request.get_json(force=True)
        # ~ except:
            # ~ args = request.form.to_dict()
        # ~ try:
            # ~ if app.isardapi.update_table_value('hypervisors', args['pk'], args['name'], args['value']):
                # ~ return json.dumps('Updated'), 200, {'ContentType':'application/json'}
            # ~ else:
                # ~ return json.dumps('This is not a valid value.'), 500, {'ContentType':'application/json'}
        # ~ except Exception as e:
            # ~ return json.dumps('Wrong parameters.'), 500, {'ContentType':'application/json'}



#~ @app.route('/stream/admin/hypers')
#~ @login_required
#~ def admin_stream_hypers():
        #~ return Response(stream_hypers(), mimetype='text/event-stream')    

#~ def stream_hypers():
        #~ with app.app_context():
            #~ for c in r.table('hypervisors').merge({"table": "hypervisors"}).changes(include_initial=False).union(
                        #~ r.table('hypervisors_status').merge({"table": "hypervisors_status"}).changes(include_initial=False)).run(db.conn):
                #~ if c['new_val'] is None:
                    #~ if c['old_val']['table'] is 'hypervisors':
                        #~ yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Deleted',time.time(),json.dumps(c['old_val']['id']))
                        #~ continue
                #~ if 'old_val' not in c:
                    #~ if c['old_val']['table'] is 'hypervisors':
                        #~ yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('New',time.time(),json.dumps(app.isardapi.f.flatten_dict(c['new_val'])))   
                        #~ continue             
                #~ if 'detail' not in c['new_val']: c['new_val']['detail']=''
                #~ yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('hypervisors',time.time(),json.dumps(app.isardapi.f.flatten_dict(c['new_val'])))

# ~ @app.route('/admin/hypervisors/get')
# ~ @login_required
# ~ @isAdmin
# ~ def hypervisors_get():
    # ~ return json.dumps(app.adminapi.hypervisors_get()), 200, {'ContentType': 'application/json'}



#~ @app.route('/admin/hypervisors_pools_add')
#~ @login_required
#~ def admin_hypervisors_pools_add():

    
