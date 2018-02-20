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
#~ from ...lib import admin_api

#~ app.adminapi = admin_api.isardAdmin()

#~ from .decorators import isAdmin

@app.route('/media', methods=['POST','GET'])
@login_required
def media():
    #~ if request.method == 'POST':
        #~ hp=request.form['hypervisors_pools']
        #~ url=request.form['url']
        #~ filename=url.split('/')[-1]
        #~ iso=app.isardapi.user_relative_disk_path(current_user.username, filename)
        #~ if not iso:
            #~ flash('Something went wrong, filename has extrange characters','danger')
            #~ return render_template('pages/media.html', nav='Media')
        #~ iso['status']='Starting'
        #~ iso['name']=request.form['name']
        #~ iso['percentage']=0
        #~ iso['url']=url
        #~ iso['hypervisor_pool']=hp
        #~ iso['user']=current_user.username
        #~ if not app.isardapi.add_dict2table(iso,'media'):
            #~ flash('Something went wrong. Upload task not scheduled')
        #~ return redirect(url_for('admin_media_upload'))
    return render_template('pages/media.html', nav='Media')

@app.route('/media/get/')
@app.route('/media/get/<kind>')
@login_required
def media_get(kind='username'):
    if kind=='username':
        return json.dumps(app.isardapi.get_user_media(current_user.username)), 200, {'ContentType': 'application/json'}
    #~ if kind=='category': 
        #~ return json.dumps(app.isardapi.get_category_domains(current_user.category)), 200, {'ContentType': 'application/json'}
    #~ if kind=='group':
        #~ return json.dumps(app.isardapi.get_group_domains(current_user.group)), 200, {'ContentType': 'application/json'}
    return url_for('media')
