# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8
from flask import render_template, Response, request, redirect, url_for
from flask_login import login_required, current_user
from .decorators import ownsid
from webapp import app
from ..lib.log import *

import rethinkdb as r
from ..lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

import time, json




# Gets all allowed for a domain
# ~ @app.route('/domain/alloweds/select2', methods=['POST'])
# ~ @login_required
# ~ def domain_alloweds_select2():
    # ~ allowed=request.get_json(force=True)['allowed']
    # ~ return json.dumps(app.isardapi.get_alloweds_select2(allowed))
       

# Will get allowed hardware resources for current_user         
@app.route('/domains/hardware/allowed', methods=['GET'])
@login_required
def domains_hardware_allowed():
    dict={}
    dict['nets']=app.isardapi.get_alloweds(current_user.username,'interfaces',pluck=['id','name','description'],order='name')
    #~ dict['disks']=app.isardapi.get_alloweds(current_user.username,'disks',pluck=['id','name','description'],order='name')
    dict['graphics']=app.isardapi.get_alloweds(current_user.username,'graphics',pluck=['id','name','description'],order='name')
    dict['videos']=app.isardapi.get_alloweds(current_user.username,'videos',pluck=['id','name','description'],order='name')
    dict['boots']=app.isardapi.get_alloweds(current_user.username,'boots',pluck=['id','name','description'],order='name')
    dict['hypervisors_pools']=app.isardapi.get_alloweds(current_user.username,'hypervisors_pools',pluck=['id','name','description'],order='name')
    dict['forced_hyps']=[]
    if current_user.role == 'admin':
        dict['forced_hyps']=app.adminapi.get_admin_table('hypervisors',['id','hostname','description','status'])
    dict['forced_hyps'].insert(0,{'id':'default','hostname':'Auto','description':'Hypervisor pool default'})
    dict['user']=app.isardapi.get_user(current_user.username)
    return json.dumps(dict)

# Get hardware for domain
@app.route('/domains/hardware', methods=['POST'])
@login_required
@ownsid
def domains_hadware():
    try:
        hs=request.get_json(force=True)['hs']
    except:
        hs=False
    try:
        return json.dumps(app.isardapi.get_domain(request.get_json(force=True)['pk'], human_size=hs, flatten=False))
    except:
        return json.dumps([])

# Who has acces to a table item     
@app.route('/alloweds/table/<table>', methods=['POST'])
@login_required
@ownsid
def alloweds_table(table):
    if table in ['domains','media']:
        print(app.adminapi.get_admin_table(table, pluck=['allowed'], id=request.get_json(force=True)['pk'], flatten=False)['allowed'])
        return json.dumps(app.adminapi.get_admin_table(table, pluck=['allowed'], id=request.get_json(force=True)['pk'], flatten=False)['allowed'])
    # ~ return json.dumps(app.isardapi.f.unflatten_dict(app.isardapi.get_domain(request.get_json(force=True)['pk']))['allowed'])


# Gets all list of roles, categories, groups and users
@app.route('/alloweds_term/<table>', methods=["POST"])
@login_required
def alloweds_table_term(table):
    if request.method == 'POST' and table in ['roles','categories','groups','users']:
        data=request.get_json(force=True)
        data['pluck']=['id','name']
        result=app.adminapi.get_admin_table_term(table,'name',data['term'],pluck=data['pluck'])
        return json.dumps(result), 200, {'ContentType':'application/json'}
    return json.dumps('Could not select.'), 500, {'ContentType':'application/json'} 
    
    



# ~ @app.route('/domain_messages', methods=['POST'])
# ~ @login_required
# ~ @ownsid
# ~ def domain_messages():
    # ~ if request.method == 'POST':
        # ~ return json.dumps(app.isardapi.get_domain_last_messages(request.get_json(force=True)['id']))
    # ~ return False

# ~ @app.route('/domain_events', methods=['POST'])
# ~ @login_required
# ~ @ownsid
# ~ def domain_events():
    # ~ if request.method == 'POST':
        # ~ return json.dumps(app.isardapi.get_domain_last_events(request.get_json(force=True)['id']))
    # ~ return False
   
# ~ @app.route('/chain', methods=['POST'])
# ~ @login_required
# ~ def chain():
    # ~ if request.method == 'POST':
        # ~ return json.dumps(app.isardapi.get_domain_backing_images(request.get_json(force=True)['id']))
    # ~ return False
           
        
        
