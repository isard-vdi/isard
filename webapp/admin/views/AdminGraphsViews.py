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
@login_required
@isAdmin
def admin_graphs_d3_bubble():
        return Response(graph_d3_bubble_stream(), mimetype='text/event-stream')
        
def graph_d3_bubble_stream():
    with app.app_context():
        domains={}
        for s in r.table('domains').get_all('Started', index='status')['id'].coerce_to('array'), 
            lamdba stats: r.table('domains_status').get_all(r.args(stats), index='name').orderBy('when').group('name').nth(-1)
            .changes(include_initial=False).run(db.conn)
        #~ r.table('domains_status').pluck('name','when','status').orderBy('when').group('name').nth(-1)
        #~ for s in r.table('domains_status').pluck('name','status').changes(include_initial=False).run(db.conn):
            print(s)
            ns=s['new_val']
            print(ns['name'],ns['status']['hyp'])
            # Falta eliminar els que ja han parat!!
            #~ if d['status'] is not 'Started':
                #~ try:
                    #~ domains.pop(ns['name'], None)
                #~ except:
                    #~ None
            #~ continue
            
            if ns['name'].startswith('_'):
                d=r.table('domains').get(ns['name']).pluck('status','os').run(db.conn)
                try:
                    os=r.table('domains').get(ns['name']).pluck('os').run(db.conn)['os']
                except:
                    os='linux'
                domains[ns['name']]=   {'hyp':ns['status']['hyp'],
                                        'load':ns['status']['cpu_usage'],
                                        'memory':ns['status']['procesed_stats']['ram_current'],
                                        'icon':os}
                yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('update',time.time(),json.dumps(domains))
