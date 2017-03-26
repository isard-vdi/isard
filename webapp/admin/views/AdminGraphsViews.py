# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json
import time

from flask import render_template, Response, request, redirect, url_for, send_from_directory
from flask_login import login_required

from webapp import app
from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

import rethinkdb as r
from ...lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from .decorators import isAdmin

'''
RENDER GRAPH ADMIN PAGE
'''
@app.route('/admin/graphs')
@login_required
@isAdmin
def admin_graphs():
    return render_template('admin/pages/graphs.html',nav="Graphs")
 
@app.route('/admin/graphs/d3_bubble')
#@login_required
#@isAdmin
def admin_graphs_d3_bubble():
        return Response(graph_d3_bubble_stream(), mimetype='text/event-stream')
        
def graph_d3_bubble_stream():
    
    with app.app_context():
        for c in r.table('domains_status').pluck('name','when','status').changes(include_initial=False).run(db.conn):
            domains={}
            if(c['new_val']['name'].startswith('_')):
                d=r.table('domains').get(c['new_val']['name']).pluck('id','name','status','hyp_started','os').run(db.conn)
                if(d['status']=='Started'):
                    domains[c['new_val']['name']]=d
                    domains[c['new_val']['name']]['status']=c['new_val']['status']
                    yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('update',time.time(),json.dumps(domains))
                else:
                    print('deleted:'+c['new_val']['name'])
                    yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('stopped',time.time(),json.dumps({'name':c['new_val']['name']}))
