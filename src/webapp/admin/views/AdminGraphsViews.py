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
@app.route('/admin/graphs/<kind>')
@login_required
@isAdmin
def admin_graphs(kind):
    return render_template('admin/pages/graphs/'+kind+'.html',nav="Graphs")
 
#~ @app.route('/admin/stream/graphs/d3_bubble')
#~ #@login_required
#~ #@isAdmin
#~ def admin_stream_graphs_d3_bubble():
        #~ return Response(graph_d3_bubble_stream(), mimetype='text/event-stream')
        
#~ def graph_d3_bubble_stream():
    
    #~ with app.app_context():
        #~ for c in r.table('domains_status').pluck('name','when','status').changes(include_initial=False).run(db.conn):
            ##domains={}
            #~ if(c['new_val']['name'].startswith('_')):
                #~ try:
                    #~ d=r.table('domains').get(c['new_val']['name']).pluck('id','name','status','hyp_started','os').run(db.conn)
                #~ except:
                    #~ d=None
                #~ if d is not None: #This if can be removed when vimet is shutdown
                    #~ if(d['status']=='Started'):
                        #~ d['status']=c['new_val']['status']
                        #~ yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('update',time.time(),json.dumps(d))
                    #~ else:
                        #~ yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('stopped',time.time(),json.dumps(d))

#~ @app.route('/admin/graph_tree_horiz')
#~ def admin_graph_tree_h():
    #~ return render_template('admin/pages/graphs_tree_horiz.html',nav="Graphs")

#~ @app.route('/admin/graph_tree_circle')
#~ def admin_graph_tree_c():
    #~ return render_template('admin/pages/graphs_tree_circle.html',nav="Graphs")
        
@app.route('/admin/graphs_data_tree')
@login_required
@isAdmin
def admin_graphs_tree():
    #~ return json.dumps(app.adminapi.get_domains_tree_list()), 200, {'ContentType': 'application/json'}
    return json.dumps(app.adminapi.get_domains_tree('_windows_7_x64_v3')), 200, {'ContentType': 'application/json'}

@app.route('/admin/graphs_data_tree_list')
@login_required
@isAdmin
def admin_graphs_tree_list():
    return json.dumps(app.adminapi.get_domains_tree_list()), 200, {'ContentType': 'application/json'}
    #~ return json.dumps(app.adminapi.get_domains_tree('_windows_7_x64_v3')), 200, {'ContentType': 'application/json'}

@app.route('/admin/engine_graphs')
@login_required
@isAdmin
def admin_gengine_graphs():
    import requests
    try:
        response = requests.get('http://localhost:5555/engine_info')
        data=response.json()
        data['dashboard']=app.adminapi.get_dashboard()
        return json.dumps(data), 200, {'ContentType': 'application/json'}
    except Exception as e:
        return json.dumps({}), 500, {'ContentType': 'application/json'}
    
    
    
