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

import rethinkdb as r
from ...lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from .decorators import isAdmin

'''
DOMAINS (NOT USED)
'''
@app.route('/admin/domains/render/<nav>')
@login_required
@isAdmin
def admin_domains(nav='Domains'):
    if nav=='Desktops': icon='desktop'
    if nav=='Templates': icon='cube'
    if nav=='Bases': icon='cubes'
    if nav=='Domains': icon='arrows-alt'
    return render_template('admin/pages/domains.html', nav=nav, icon=icon) 

@app.route('/admin/mdomains', methods=['POST'])
@login_required
@isAdmin
def admin_mdomains():
    dict=request.get_json(force=True)
    print('vamoo')
    #~ original_domains=app.adminapi.multiple_action('domains',dict['action'],dict['ids'])
    desktop_domains=app.adminapi.multiple_check_field('domains','kind','desktop',dict['ids'])
    res=app.adminapi.multiple_action('domains',dict['action'],desktop_domains)
    print(res)
    return json.dumps({'test':1}), 200, {'ContentType': 'application/json'}
    
@app.route('/admin/domains/get/<kind>')
@app.route('/admin/domains/get')
@login_required
@isAdmin
def admin_domains_get(kind=False):
    if kind:
        if kind=='Desktops': kind='desktop'
        if kind=='Templates': 
            return json.dumps(app.adminapi.get_admin_domains_with_derivates('template')), 200, {'ContentType': 'application/json'}
        if kind=='Bases':
            return json.dumps(app.adminapi.get_admin_domains_with_derivates('base')), 200, {'ContentType': 'application/json'}
    return json.dumps(app.adminapi.get_admin_domains(kind)), 200, {'ContentType': 'application/json'}




'''
VIRT BUILDER TESTS (IMPORT NEW BUILDERS?)
'''
@app.route('/admin/domains/virtrebuild')
@login_required
@isAdmin
def admin_domains_get_builders():
    #~ import subprocess
    #~ command_output=subprocess.getoutput(['virt-builder --list'])
    #~ blist=[]
    #~ for l in command_output.split('\n'):
            #~ blist.append({'dwn':False,'id':l[0:24].strip(),'arch':l[25:35].strip(),'name':l[36:].strip()})
    #~ app.adminapi.cmd_virtbuilder('cirros-0.3.1','/isard/cirros.qcow2','1')
    app.adminapi.update_virtbuilder()
    app.adminapi.update_virtinstall()
    #~ images=app.adminapi.get_admin_table('domains_virt_builder')
    return json.dumps(''), 200, {'ContentType': 'application/json'}


