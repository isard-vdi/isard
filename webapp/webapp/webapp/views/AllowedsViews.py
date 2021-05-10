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

from ..lib.quotas import QuotaLimits
quotas = QuotaLimits()


# Gets all allowed for a domain
# ~ @app.route('/isard-admin/domain/alloweds/select2', methods=['POST'])
# ~ @login_required
# ~ def domain_alloweds_select2():
    # ~ allowed=request.get_json(force=True)['allowed']
    # ~ return json.dumps(app.isardapi.get_alloweds_select2(allowed))
       

# Will get allowed hardware resources for current_user         
@app.route('/isard-admin/domains/hardware/allowed', methods=['GET'])
@login_required
def domains_hardware_allowed():
    return json.dumps(quotas.user_hardware_allowed(current_user.id))

# Will get allowed hardware quota max resources for current_user         
@app.route('/isard-admin/<kind>/quotamax', methods=['GET'])
@app.route('/isard-admin/<kind>/quotamax/<id>', methods=['GET'])
@login_required
def user_quota_max(kind,id=False):
    if kind == 'user':
        if id == False:
            id=current_user.id
        #return json.dumps(quotas.get(id))
        return json.dumps(quotas.get_user(id))

    if kind == 'category':
        if id == False:
            id=current_user.category
        #return json.dumps(app.isardapi.process_category_limits(id))
        return json.dumps(quotas.get_category(id))

    if kind == 'group':
        if id == False:
            id=current_user.group
        #return json.dumps(app.isardapi.process_group_limits(id))
        return json.dumps(quotas.get_group(id)) 



# Get hardware for domain
@app.route('/isard-admin/domains/hardware', methods=['POST'])
@login_required
#@ownsid

def domains_hadware():
    try:
        hs=request.get_json(force=True)['hs']
    except:
        hs=False
    try:
        hardware=app.isardapi.get_domain_create_dict(request.get_json(force=True)['pk'], human_size=hs, flatten=False)
        hardware['hardware']['memory']=hardware['hardware']['memory']/1048576
        return json.dumps(hardware)
    except:
        return json.dumps([])

# Who has acces to a table item     
@app.route('/isard-admin/alloweds/table/<table>', methods=['POST'])
@login_required
@ownsid
def alloweds_table(table):
    return json.dumps(app.isardapi.get_alloweds_select2(app.adminapi.get_admin_table(table, pluck=['allowed'], id=request.get_json(force=True)['pk'], flatten=False)['allowed']))


# Gets all list of roles, categories, groups and users from a 2+ chars term
@app.route('/isard-admin/alloweds/term/<table>', methods=["POST"])
@login_required
def alloweds_table_term(table):
    if request.method == 'POST' and table in ['roles','categories','groups','users']:
        data=request.get_json(force=True)
        data['pluck']=['id','name']
        if current_user.role == "admin":
            if table == 'groups':
                result=app.adminapi.get_admin_table_term(table,'id',data['term'],pluck=['id','name','parent_category'])
            elif table == 'users':
                result=app.adminapi.get_admin_table_term(table,'id',data['term'],pluck=['id','name','uid'])
            else:
                result=app.adminapi.get_admin_table_term(table,'name',data['term'],pluck=data['pluck'])
        else:
            if table == 'roles':
                result=app.adminapi.get_admin_table_term(table,'name',data['term'],pluck=data['pluck'])
            if table == 'categories':
                result=app.adminapi.get_admin_table_term(table,'name',data['term'],pluck=data['pluck'])
                result = [c for c in result if c['id'] == current_user.category]
            if table == 'groups':
                result=app.adminapi.get_admin_table_term(table,'id',data['term'],pluck=['id','name','parent_category'])
                result = [g for g in result if g['id'].startswith(current_user.category)] 
            if table == 'users':
                result=app.adminapi.get_admin_table_term(table,'name',data['term'],pluck=['id','name','category', 'uid'])
                result = [u for u in result if u['category'] == current_user.category]                               
        return json.dumps(result), 200, {'ContentType':'application/json'}
    return json.dumps('Could not select.'), 500, {'ContentType':'application/json'} 
    

@app.route('/isard-admin/domains/removable', methods=['POST'])
@login_required
@ownsid
def domain_removable():
    if request.method == 'POST':
        return json.dumps(app.adminapi.is_template_removable(request.get_json(force=True)['id'],current_user.id))
    return json.dumps('Could not check.'), 500, {'ContentType':'application/json'} 
