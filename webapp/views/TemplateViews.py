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
@app.route('/templates/get/<kind>')
@login_required
def templates_get(kind='username'):
	return json.dumps(app.isardapi.get_user_templates(current_user.username)), 200, {'ContentType': 'application/json'}

@app.route('/stream/templates')
@login_required
@checkRole
def sse_request_templates():
        return Response(event_stream_templates(current_user.username), mimetype='text/event-stream')

import random
def event_stream_templates(username):
        with app.app_context():
            for c in r.table('domains').get_all(username, index='user').filter((r.row["kind"] == 'user_template') | (r.row["kind"] == 'public_template')).pluck({'id', 'name','icon','kind','description'}).changes(include_initial=True).run(db.conn):
                if c['new_val'] is None:
                    yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Deleted',time.time(),json.dumps(c['old_val']['id']))
                    continue
                if 'old_val' not in c:
                    yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('New',time.time(),json.dumps(c['new_val']))   
                    continue             
                if 'detail' not in c['new_val']: c['new_val']['detail']=''
                c['new_val']['derivates']=app.isardapi.get_domain_derivates(c['new_val']['id'])
                yield 'retry: 2000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Status',time.time(),json.dumps(c['new_val']))
                yield 'retry: 2000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Quota',time.time(),json.dumps(qdict))

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
            if app.isardapi.toggle_template_kind(current_user.username,args['pk']):
                return json.dumps('Updated'), 200, {'ContentType':'application/json'}
            else:
                return json.dumps('Something went wrong.'), 500, {'ContentType':'application/json'}
        except Exception as e:
            return json.dumps('Wrong parameters.'), 500, {'ContentType':'application/json'}
