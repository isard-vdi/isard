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

@app.route('/isos', methods=['GET'])
def isos():
    #~ if request.method == 'POST':
        #~ hp=request.form['hypervisors_pools']
        #~ url=request.form['url']
        #~ filename=url.split('/')[-1]
        #~ iso=app.isardapi.user_relative_disk_path(current_user.username, filename)
        #~ print(iso)
        #~ if not iso:
            #~ flash('Something went wrong, filename has extrange characters','danger')
            #~ return render_template('pages/isos.html', nav='Isos')
        #~ iso['status']='Starting'
        #~ iso['name']=request.form['name']
        #~ iso['percentage']=0
        #~ iso['url']=url
        #~ iso['hypervisor_pool']=hp
        #~ iso['user']=current_user.username
        #~ print(iso)
        #~ if not app.isardapi.add_dict2table(iso,'isos'):
            #~ flash('Something went wrong. Upload task not scheduled')
        #~ return redirect(url_for('isos_upload'))
    return render_template('pages/isos.html', nav='Isos')

#~ @app.route('/stream/isos')
#~ @login_required
#~ def sse_request_isos():
        #~ return Response(event_stream(current_user.username), mimetype='text/event-stream')

#~ def event_stream_isos(username):
        #~ with app.app_context():
            #~ for c in r.table('isos').get_all(username, index='user').changes(include_initial=True).run(db.conn):
                #~ if c['new_val'] is None:
                    #~ yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Deleted',time.time(),json.dumps(c['old_val']['id']))
                    #~ continue
                #~ if 'old_val' not in c:
                    #~ yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('New',time.time(),json.dumps(app.isardapi.f.flatten_dict(c['new_val'])))   
                    #~ continue             
                #~ if 'detail' not in c['new_val']: c['new_val']['detail']=''
                #~ yield 'retry: 2000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Status',time.time(),json.dumps(app.isardapi.f.flatten_dict(c['new_val'])))


