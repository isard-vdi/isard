# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json
import time

from flask import render_template, Response, request
from flask_login import login_required, current_user

from webapp import app
from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

from .decorators import isAdmin

'''
DOMAINS (NOT USED)
'''
@app.route('/admin/domains/render/<nav>')
@login_required
@isAdmin
def admin_domains(nav='Domains'):
    icon=''
    if nav=='Desktops': icon='desktop'
    if nav=='Templates': icon='cube'
    if nav=='Bases': icon='cubes'
    if nav=='Resources': 
        icon='arrows-alt'
        return render_template('admin/pages/domains_resources.html', title=nav, nav=nav, icon=icon) 
    else:
        return render_template('admin/pages/domains.html', title=nav, nav=nav, icon=icon) 

@app.route('/admin/mdomains', methods=['POST'])
@login_required
@isAdmin
def admin_mdomains():
    dict=request.get_json(force=True)
    #~ original_domains=app.adminapi.multiple_action('domains',dict['action'],dict['ids'])
    desktop_domains=app.adminapi.multiple_check_field('domains','kind','desktop',dict['ids'])
    res=app.adminapi.multiple_action('domains',dict['action'],desktop_domains)
    # ~ print(res)
    return json.dumps({'test':1}), 200, {'ContentType': 'application/json'}
    
@app.route('/admin/domains/get/<kind>')
@app.route('/admin/domains/get')
@login_required
@isAdmin
def admin_domains_get(kind=False):
    if kind:
        if kind=='Desktops': 
            # ~ print('im a desktop kind')
            kind='desktop'
            #~ for d in app.adminapi.get_admin_domains(kind):
                #~ print(len(d['history_domain']))
        if kind=='Templates': 
            return json.dumps(app.adminapi.get_admin_domains_with_derivates(kind='template')), 200, {'ContentType': 'application/json'}
        if kind=='Bases':
            return json.dumps(app.adminapi.get_admin_domains_with_derivates(kind='base')), 200, {'ContentType': 'application/json'}
    return json.dumps(app.adminapi.get_admin_domains_with_derivates(kind=kind)), 200, {'ContentType': 'application/json'}

@app.route('/admin/domains/xml/<id>', methods=['POST','GET'])
@login_required
@isAdmin
def admin_domains_xml(id):
    if request.method == 'POST':
        res=app.adminapi.update_table_dict('domains',id,request.get_json(force=True))
        if res:
            return json.dumps(res), 200,  {'ContentType': 'application/json'}
        else:
            return json.dumps(res), 500,  {'ContentType': 'application/json'}
    return json.dumps(app.adminapi.get_admin_table('domains',pluck='xml',id=id)['xml']), 200, {'ContentType': 'application/json'}


@app.route('/admin/domains/events/<id>', methods=['GET'])
@login_required
@isAdmin
def admin_domains_events(id):
    return json.dumps(app.isardapi.get_domain_last_events(id)), 200, {'ContentType': 'application/json'}

@app.route('/admin/domains/messages/<id>', methods=['GET'])
@login_required
@isAdmin
def admin_domains_messages(id):
    return json.dumps(app.isardapi.get_domain_last_messages(id)), 200, {'ContentType': 'application/json'}    

@app.route('/admin/domains/todelete', methods=['POST'])
@app.route('/admin/domains/todelete/<id>', methods=['GET'])
@login_required
@isAdmin
def admin_domains_todelete(id=None):
    if request.method == 'POST':
        res=app.adminapi.domains_mdelete(request.get_json(force=True))
        if res:
            return json.dumps(res), 200,  {'ContentType': 'application/json'}
        else:
            return json.dumps(res), 500,  {'ContentType': 'application/json'}
    return json.dumps(app.adminapi.template_delete_list(id)), 200, {'ContentType': 'application/json'}


# ~ '''
# ~ VIRT BUILDER TESTS (IMPORT NEW BUILDERS?)
# ~ '''
# ~ @app.route('/admin/domains/virtrebuild')
# ~ @login_required
# ~ @isAdmin
# ~ def admin_domains_get_builders():
    # ~ app.adminapi.update_virtbuilder()
    # ~ app.adminapi.update_virtinstall()
    # ~ return json.dumps(''), 200, {'ContentType': 'application/json'}


