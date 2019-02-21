# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json

from flask import render_template, Response, request, redirect, url_for
from flask_login import login_required, current_user

from webapp import app

from ..lib.log import *

@app.route('/media', methods=['GET'])
@login_required
def media():
    return render_template('pages/media.html', nav='Media')

@app.route('/media/get/')
@login_required
def media_get():
	data=app.isardapi.get_all_alloweds_table('media',current_user.username, pluck=False)
	# ~ data=[d for d in data if d['status']=='Downloaded' ]
	return json.dumps(data), 200, {'ContentType': 'application/json'}

@app.route('/domain/media', methods=["POST"])
@login_required
def domain_media():
    if request.method == 'POST':
        data=request.get_json(force=True)    
        return json.dumps(app.isardapi.get_domain_media(data['pk'])), 200, {'ContentType': 'application/json'}
    return url_for('media')
     
@app.route('/media/installs')
@login_required
def media_installs_get():
    return json.dumps(app.isardapi.get_media_installs()), 200, {'ContentType': 'application/json'}


@app.route('/media/select2/post', methods=["POST"])
@login_required
def media_select2_post():
    if request.method == 'POST':
        data=request.get_json(force=True)
        if 'pluck' not in data.keys():
            data['pluck']=False
        if data['kind'] == 'isos': kind = 'iso'
        if data['kind'] == 'floppies': kind = 'floppy'
        #~ if 'order' not in data.keys():
            #~ data['order']=False
        result=app.isardapi.get_all_table_allowed_term('media',kind,'name',data['term'],current_user.username,pluck=data['pluck'])
        #~ result=app.adminapi.get_admin_table_term('media','name',data['term'],kind=kind,pluck=data['pluck'])
        return json.dumps(result), 200, {'ContentType':'application/json'}
    return json.dumps('Could not select.'), 500, {'ContentType':'application/json'} 


# ~ @app.route('/admin/table/<table>/post', methods=["POST"])
# ~ @login_required
# ~ @isAdmin
# ~ def admin_table_post(table):
    # ~ if request.method == 'POST':
        # ~ data=request.get_json(force=True)
        # ~ if 'pluck' not in data.keys():
            # ~ data['pluck']=False
        # ~ #~ if 'order' not in data.keys():
            # ~ #~ data['order']=False
        # ~ result=app.adminapi.get_admin_table_term(table,'name',data['term'],pluck=data['pluck'])
        # ~ return json.dumps(result), 200, {'ContentType':'application/json'}
    # ~ return json.dumps('Could not delete.'), 500, {'ContentType':'application/json'} 
