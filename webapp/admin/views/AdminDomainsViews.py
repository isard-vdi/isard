# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json
import time

from flask import render_template, Response, request
from flask_login import login_required, current_user

from webapp import app
from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

import rethinkdb as r
from ...lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from .decorators import isAdmin

'''
DOMAINS
'''
@app.route('/admin/domains')
@login_required
@isAdmin
def admin_domains():
    return render_template('admin/pages/domains.html', nav="Domains") 

@app.route('/admin/mdomains', methods=['POST'])
@login_required
@isAdmin
def admin_mdomains():
    print(request.get_json(force=True))
    return json.dumps({}), 200, {'ContentType': 'application/json'}
    
@app.route('/admin/domains/get')
@login_required
@isAdmin
def admin_domains_get():
    return json.dumps(app.adminapi.get_admin_domains()), 200, {'ContentType': 'application/json'}

#~ @app.route('/admin/domains/datatables')
#~ @login_required
#~ @isAdmin
#~ def admin_domains_datatables():
    #~ return json.dumps(app.adminapi.get_admin_domain_datatables()), 200, {'ContentType': 'application/json'}

#~ @app.route('/admin/interfaces/get')
#~ @login_required
#~ @isAdmin
#~ def admin_interfaces_get():
    #~ return json.dumps(app.adminapi.get_admin_networks()), 200, {'ContentType': 'application/json'}
   
@app.route('/admin/stream/domains')
@login_required
@isAdmin
def admin_stream_domains():
        return Response(admin_domains_stream(), mimetype='text/event-stream')

def admin_domains_stream():
        #~ initial=True
        with app.app_context():
            for c in r.table('domains').merge({"table": "domains"}).changes(include_initial=False).union(
                r.table('domains_status').pluck('id').merge({"table": "domains_status"}).changes(include_initial=False)).run(db.conn):  
                if (c['new_val'] is not None and c['new_val']['table']=='domains') or (c['old_val'] is not None and c['old_val']['table']=='domains'):
                    if c['new_val'] is None:
                        try:
                            yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Deleted',time.time(),json.dumps(c['old_val']))
                            continue
                        except:
                            break
                    if c['old_val'] is None:
                        try:
                            yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('New',time.time(),json.dumps(app.isardapi.f.flatten_dict(c['new_val'])))   
                            continue 
                        except:
                            break
                    #~ if 'detail' not in c['new_val']: c['new_val']['detail']=''
                    try:
                        yield 'retry: 2000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Status',time.time(),json.dumps(app.isardapi.f.flatten_dict(c['new_val'])))
                    except:
                        break
                else:
                    try:
                        yield 'event: %s\nid: %d\ndata: ''\n\n' % ('conn',time.time())
                    except:
                        log.info('Exiting thread disposable')
                        break
