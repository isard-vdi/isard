# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8
from flask import render_template, Response, request, redirect, url_for, stream_with_context, flash
from webapp import app
from flask_login import login_required, login_user, logout_user, current_user
import time
import json

from ..lib.log import *

import rethinkdb as r
from ..lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from .decorators import ownsid

@app.route('/isos/upload', methods=['POST','GET'])
def isos_upload():
    if request.method == 'POST':
        hp=request.form['hypervisors_pools']
        url=request.form['url']
        filename=url.split('/')[-1]
        iso=app.isardapi.user_relative_disk_path(current_user.username, filename)
        if not iso:
            flash('Something went wrong, filename has extrange characters','danger')
            return render_template('pages/isos.html', nav='Isos')
        iso['status']='Starting'
        iso['name']=request.form['name']
        iso['percentage']=0
        iso['url']=url
        iso['hypervisor_pool']=hp
        iso['user']=current_user.username
        if not app.isardapi.add_dict2table(iso,'isos'):
            flash('Something went wrong. Upload task not scheduled')
        return redirect(url_for('isos_upload'))
    return render_template('pages/isos.html', nav='Isos')

@app.route('/stream/isos')
@login_required
def sse_request_isos():
        return Response(event_stream(current_user.username), mimetype='text/event-stream')

def event_stream_isos(username):
        with app.app_context():
            for c in r.table('isos').get_all(username, index='user').merge({"table": "domains"}).changes(include_initial=True).union(
                r.table('domains_status').pluck('id').merge({"table": "domains_status"}).changes(include_initial=False)).run(db.conn):  
                if (c['new_val'] is not None and c['new_val']['table']=='isos') or (c['old_val'] is not None and c['old_val']['table']=='isos'):

                    if c['new_val'] is None:
                        try:
                            yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Deleted',time.time(),json.dumps(c['old_val']['id']))
                            continue
                        except:
                            break
                    if 'old_val' not in c:
                        try:
                            yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('New',time.time(),json.dumps(app.isardapi.f.flatten_dict(c['new_val'])))   
                            continue
                        except:
                            break
                    try:
                        yield 'retry: 2000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Status',time.time(),json.dumps(app.isardapi.f.flatten_dict(c['new_val'])))
                    except:
                        break
                else:
                    try:
                        yield 'event: %s\nid: %d\ndata: ''\n\n' % ('conn',time.time())
                    except:
                        log.info('Exiting thread isos')
                        break

