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
LANDING ADMIN PAGE
'''
@app.route('/admin')
@login_required
@isAdmin
def admin():
    return render_template('admin/pages/hypervisors.html', title="Hypervisors", header="Hypervisors", nav="Hypervisors")
 
@app.route('/admin/table/<table>/get')
@login_required
@isAdmin
def admin_table_get(table):
    result=app.adminapi.get_admin_table(table)
    if table == 'scheduler_jobs': 
        for i,val  in enumerate(result):
            result[i].pop('job_state', None)
    return json.dumps(result), 200, {'ContentType':'application/json'} 

# Used in quota.js for admin users
@app.route('/admin/tabletest/<table>/post', methods=["POST"])
@login_required
@isAdmin
def admin_tabletest_post(table):
    if request.method == 'POST':
        data=request.get_json(force=True)
        if 'id' not in data.keys():
            data['id']=False        
        if 'pluck' not in data.keys():
            data['pluck']=False
        if 'order' not in data.keys():
            data['order']=False
        if 'flatten' not in data.keys():
            data['flatten']=True
        result=app.adminapi.get_admin_table(table,id=data['id'],pluck=data['pluck'],order=data['order'],flatten=data['flatten'])
        return json.dumps(result), 200, {'ContentType':'application/json'}
    return json.dumps('Could not delete.'), 500, {'ContentType':'application/json'} 
    
@app.route('/admin/table/<table>/post', methods=["POST"])
@login_required
@isAdmin
def admin_table_post(table):
    if request.method == 'POST':
        data=request.get_json(force=True)
        if 'pluck' not in data.keys():
            data['pluck']=False
        if 'kind' not in data.keys():
            data['kind']=False
        # ~ else:
            # ~ if data['kind']=='template':
                # ~ result=app.adminapi.get_admin_table_term(table,'name',data['term'],pluck=data['pluck'],kind=data['kind'])
                # ~ result=app.adminapi.get_admin_table_term(table,'name',data['term'],pluck=data['pluck'],kind=data['kind'])
                # ~ result=app.adminapi.get_admin_table_term(table,'name',data['term'],pluck=data['pluck'],kind=data['kind'])
        # ~ else:
            # ~ if data['kind']='not_desktops':
                # ~ result=app.adminapi.get_admin_table_term(table,'name',data['term'],pluck=data['pluck'],kind=)
        #~ if 'order' not in data.keys():
            #~ data['order']=False
        result=app.adminapi.get_admin_table_term(table,'name',data['term'],pluck=data['pluck'],kind=data['kind'])
        return json.dumps(result), 200, {'ContentType':'application/json'}
    return json.dumps('Could not delete.'), 500, {'ContentType':'application/json'} 

@app.route('/admin/getAllTemplates', methods=["POST"])
@login_required
@isAdmin
def admin_get_all_templates():
    if request.method == 'POST':
        data=request.get_json(force=True)
        result=app.adminapi.get_admin_templates(data['term'])
        return json.dumps(result), 200, {'ContentType':'application/json'}
    return json.dumps('Could not delete.'), 500, {'ContentType':'application/json'} 
    
@app.route('/admin/delete', methods=["POST"])
@login_required
@isAdmin
def admin_delete():
    if request.method == 'POST':
        if app.adminapi.delete_table_key(request.get_json(force=True)['table'],request.get_json(force=True)['pk']):
            return json.dumps('Deleted'), 200, {'ContentType':'application/json'} 
    return json.dumps('Could not delete.'), 500, {'ContentType':'application/json'}
'''
CONFIG
'''
@app.route('/admin/config', methods=["GET", "POST"])
@login_required
@isAdmin
def admin_config():
    if request.method == 'POST':
        return json.dumps(app.adminapi.get_admin_config(1)), 200, {'ContentType': 'application/json'}
    return render_template('admin/pages/config.html',nav="Config")


#~ @app.route('/admin/disposables', methods=["POST"])
#~ @login_required
#~ @isAdmin
#~ def admin_disposables():
    #~ result=app.adminapi.get_admin_table('disposables')
    #~ return json.dumps(result), 200, {'ContentType':'application/json'} 

@app.route('/admin/config/update', methods=['POST'])
@login_required
@isAdmin
def admin_config_update():
    if request.method == 'POST':
        dict=app.isardapi.f.unflatten_dict(request.form)
        if 'auth' in dict:
            dict['auth']['local']={'active':False} if 'local' not in dict['auth']  else {'active':True}
            dict['auth']['ldap']['active']=False if 'active' not in dict['auth']['ldap'] else True
        if 'engine' in dict:
            if 'grafana' in dict['engine']:
                dict['engine']['grafana']['active']=False if 'active' not in dict['engine']['grafana'] else True
            if 'ssh' in dict['engine']:
                if 'hidden' in dict['engine']['ssh']:
                    dict['engine']['ssh']['paramiko_host_key_policy_check']=True if 'paramiko_host_key_policy_check' in dict['engine']['ssh'] else False
                    dict['engine']['ssh'].pop('hidden',None)
        if 'disposable_desktops' in dict:
            dict['disposable_desktops'].pop('id',None)
            dict['disposable_desktops']['active']=False if 'active' not in dict['disposable_desktops'] else True
        if app.adminapi.update_table_dict('config',1,dict):
            # ~ return json.dumps('Updated'), 200, {'ContentType':'application/json'}
            return render_template('admin/pages/config.html',nav="Config")
    return json.dumps('Could not update.'), 500, {'ContentType':'application/json'}

@app.route('/admin/disposable/add', methods=['POST'])
@login_required
@isAdmin
def admin_disposable_add():
    if request.method == 'POST':
        dsps=[]
        #~ Next 2 lines should be removed when form returns a list
        nets=[request.form['nets']]
        #~ print(request.form)
        disposables=request.form.getlist('disposables')
        #~ disposables=[request.form['disposables']]
        for d in disposables:
            dsps.append(app.adminapi.get_admin_table('domains',pluck=['id','name','description'],id=d))
        disposable=[{'id': app.isardapi.parse_string(request.form['name']),
                        'active':True,
                        'name': request.form['name'],
                        'description': request.form['description'],
                        'nets':nets,
                        'disposables':dsps}]
        if app.adminapi.insert_table_dict('disposables',disposable):
            return json.dumps('Updated'), 200, {'ContentType':'application/json'}
    return json.dumps('Could not update.'), 500, {'ContentType':'application/json'}
    
#~ @app.route('/admin/config/checkport', methods=['POST'])
#~ @login_required
#~ @isAdmin
#~ def admin_config_checkport():
    #~ if request.method == 'POST':
        
        #~ if app.adminapi.check_port(request.form['server'],request.form['port']):
            #~ return json.dumps('Port is open'), 200, {'ContentType':'application/json'}
    #~ return json.dumps('Port is closed'), 500, {'ContentType':'application/json'}

'''
BACKUP & RESTORE
'''
@app.route('/admin/backup', methods=['POST'])
@login_required
@isAdmin
def admin_backup():
    if request.method == 'POST':
        app.adminapi.backup_db()
        return json.dumps('Updated'), 200, {'ContentType':'application/json'}
    return json.dumps('Method not allowed.'), 500, {'ContentType':'application/json'}

@app.route('/admin/restore', methods=['POST'])
@login_required
@isAdmin
def admin_restore():
    if request.method == 'POST':
        app.adminapi.restore_db(request.get_json(force=True)['pk'])
        return json.dumps('Updated'), 200, {'ContentType':'application/json'}
    return json.dumps('Method not allowed.'), 500, {'ContentType':'application/json'}

@app.route('/admin/restore/<table>', methods=['POST'])
@login_required
@isAdmin
def admin_restore_table(table):
    global backup_data,backup_db
    if request.method == 'POST':
        #~ print(table)
        data=request.get_json(force=True)['data']
        insert=data['new_backup_data']
        data.pop('new_backup_data',None)
        #~ print(data)
        if insert:
            if app.adminapi.insert_table_dict(table,data):
                return json.dumps('Inserted'), 200, {'ContentType':'application/json'}
        else:
            id=data['id']
            data.pop('id',None)
            if app.adminapi.update_table_dict(table,id,data):
                return json.dumps('Updated'), 200, {'ContentType':'application/json'}
    return json.dumps('Method not allowed.'), 500, {'ContentType':'application/json'}
    
@app.route('/admin/backup_remove', methods=['POST'])
@login_required
@isAdmin
def admin_backup_remove():
    if request.method == 'POST':
        app.adminapi.remove_backup_db(request.get_json(force=True)['pk'])
        return json.dumps('Updated'), 200, {'ContentType':'application/json'}
    return json.dumps('Method not allowed.'), 500, {'ContentType':'application/json'}

backup_data = {}
backup_db=[]

@app.route('/admin/backup_info', methods=['POST'])
@login_required
@isAdmin
def admin_backup_info():
    global backup_data,backup_db
    if request.method == 'POST':
        backup_data,backup_db=app.adminapi.info_backup_db(request.get_json(force=True)['pk'])
        return json.dumps(backup_data), 200, {'ContentType':'application/json'}
    return json.dumps('Method not allowed.'), 500, {'ContentType':'application/json'}

@app.route('/admin/backup_detailinfo', methods=['POST'])
@login_required
@isAdmin
def admin_backup_detailinfo():
    global backup_data,backup_db
    if request.method == 'POST':
        table=request.get_json(force=True)['table']
        new_db=app.adminapi.check_new_values(table,backup_db[table])
        return json.dumps(new_db), 200, {'ContentType':'application/json'}
    return json.dumps('Method not allowed.'), 500, {'ContentType':'application/json'}
    
    
@app.route('/admin/backup/download/<id>', methods=['GET'])
@login_required
@isAdmin
def admin_backup_download(id):
    filedir,filename,data=app.adminapi.download_backup(id)
    return Response( data,
        mimetype="application/x-gzip",
        headers={"Content-Disposition":"attachment;filename="+filename})

@app.route('/admin/backup/upload', methods=['POST'])
@login_required
@isAdmin
def admin_backup_upload():
    for f in request.files:
        app.adminapi.upload_backup(request.files[f])
    return json.dumps('Updated'), 200, {'ContentType':'application/json'}


#~ @app.route('/admin/stream/<table>')
#~ @login_required
#~ @isAdmin
#~ def admin_stream_table(table):
    #~ return Response(admin_table_stream(table), mimetype='text/event-stream')

#~ def admin_table_stream(table):
    #~ with app.app_context():
        #~ for c in r.table(table).changes(include_initial=False).run(db.conn):
            #~ if c['new_val'] is None:
                #~ yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Deleted',time.time(),json.dumps(c['old_val']))
                #~ continue
            #~ c['new_val'].pop('job_state', None)                
            #~ if c['old_val'] is None:
                #~ yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('New',time.time(),json.dumps(app.isardapi.f.flatten_dict(c['new_val'])))   
                #~ continue             
            #~ yield 'retry: 2000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Status',time.time(),json.dumps(app.isardapi.f.flatten_dict(c['new_val'])))
               

#~ @app.route('/admin/stream/backups')
#~ @login_required
#~ @isAdmin
#~ def admin_stream_backups():
    #~ return Response(admin_backups_stream(), mimetype='text/event-stream')

#~ def admin_backups_stream():
    #~ with app.app_context():
        #~ for c in r.table('backups').changes(include_initial=False).run(db.conn):
            #~ if c['new_val'] is None:
                #~ yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Deleted',time.time(),json.dumps(c['old_val']))
                #~ continue
            #~ if c['old_val'] is None:
                #~ yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('New',time.time(),json.dumps(app.isardapi.f.flatten_dict(c['new_val'])))   
                #~ continue             
            #~ yield 'retry: 2000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Status',time.time(),json.dumps(app.isardapi.f.flatten_dict(c['new_val'])))
                    

#~ '''
#~ SCHEDULER
#~ '''
#~ @app.route('/admin/scheduler', methods=['POST'])
#~ @login_required
#~ @isAdmin
#~ def admin_scheduler():
    #~ if request.method == 'POST':
        #~ app.scheduler.add_scheduler(request.form['kind'],request.form['action'],request.form['hour'],request.form['minute'])        
        #~ return json.dumps('Updated'), 200, {'ContentType':'application/json'}
    #~ return json.dumps('Method not allowed.'), 500, {'ContentType':'application/json'}

#~ @app.route('/admin/stream/scheduler')
#~ @login_required
#~ @isAdmin
#~ def admin_stream_scheduler():
    #~ return Response(admin_scheduler_stream(), mimetype='text/event-stream')

#~ def admin_scheduler_stream():
    #~ with app.app_context():
        #~ for c in r.table('scheduler_jobs').changes(include_initial=False).run(db.conn):
            #~ if c['new_val'] is None:
                #~ c['old_val'].pop('job_state', None)
                #~ yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Deleted',time.time(),json.dumps(c['old_val']))
                #~ continue
            #~ if c['old_val'] is None:
                #~ c['new_val'].pop('job_state', None)
                #~ yield 'retry: 5000\nevent: %s\nid: %d\ndata: %s\n\n' % ('New',time.time(),json.dumps(app.isardapi.f.flatten_dict(c['new_val'])))   
                #~ continue             
            #~ c['new_val'].pop('job_state', None)
            #~ c['old_val'].pop('job_state', None)
            #~ yield 'retry: 2000\nevent: %s\nid: %d\ndata: %s\n\n' % ('Status',time.time(),json.dumps(app.isardapi.f.flatten_dict(c['new_val'])))
                    
