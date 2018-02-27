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

@app.route('/media', methods=['POST','GET'])
@login_required
def media():
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


@app.route('/media/installs')
@login_required
def media_installs_get():
    return json.dumps(app.isardapi.get_media_installs()), 200, {'ContentType': 'application/json'}
