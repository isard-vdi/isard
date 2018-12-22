# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8  
from flask import render_template, Response, request, redirect, url_for, stream_with_context
from webapp import app
from flask_login import login_required, login_user, logout_user, current_user
import time
import json

from ..lib.log import *
                                
import rethinkdb as r
from ..lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from .decorators import ownsid, checkRole

@app.route('/templates')
@login_required
@checkRole
def templates():
    return render_template('pages/templates.html', nav="Templates")

@app.route('/templates/get/')
@login_required
def templates_get():
	return json.dumps(app.isardapi.get_user_templates(current_user.username)), 200, {'ContentType': 'application/json'}

@app.route('/template/togglekind', methods=['POST'])
@login_required
@ownsid
def templates_kind():
    if request.method == 'POST':
        
        try:
            args = request.get_json(force=True)
        except:
            args = request.form.to_dict()
        try:
            if app.isardapi.template_kind_toggle(current_user.username,args['pk']):
                return json.dumps('Updated'), 200, {'ContentType':'application/json'}
            else:
                return json.dumps('Something went wrong.'), 500, {'ContentType':'application/json'}
        except Exception as e:
            return json.dumps('Wrong parameters.'), 500, {'ContentType':'application/json'}
