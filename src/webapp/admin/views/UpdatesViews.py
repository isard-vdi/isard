# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json

from flask import render_template, Response, request, redirect, url_for, flash
from flask_login import login_required, login_user, logout_user, current_user

from webapp import app
from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

from ...lib.isardUpdates import Updates
u=Updates()

from .decorators import isAdmin

@app.route('/admin/updates', methods=['GET'])
@login_required
@isAdmin
def admin_updates():
    if not u.is_conected():
        flash("There is a network or update server error at the moment. Try again later.","error")
        return render_template('admin/pages/updates.html', title="Updates", nav="Updates", registered=False, connected=False)    
    registered=u.is_registered()
    if not registered:
        flash("IsardVDI hasn't been registered yet.","error")
    return render_template('admin/pages/updates.html', title="Updates", nav="Updates", registered=registered, connected=True)

@app.route('/admin/updates_register', methods=['POST'])
@login_required
@isAdmin
def admin_updates_register():
    if request.method == 'POST':
        try:
            if not u.is_registered():
                u.register()
        except Exception as e:
            log.error('Error registering client: '+str(e))
            #~ return False
    if not u.is_conected():
        flash("There is a network or update server error at the moment. Try again later.","error")
        return render_template('admin/pages/updates.html', title="Updates", nav="Updates", registered=False, connected=False)    
    registered=u.is_registered()
    if not registered:
        flash("IsardVDI hasn't been registered yet.","error")
    return render_template('admin/pages/updates.html', title="Updates", nav="Updates", registered=registered, connected=True)

@app.route('/admin/updates_reload', methods=['POST'])
@login_required
@isAdmin
def admin_updates_reload():
    if request.method == 'POST':
        u.reload_updates()
    if not u.is_conected():
        flash("There is a network or update server error at the moment. Try again later.","error")
        return render_template('admin/pages/updates.html', title="Updates", nav="Updates", registered=False, connected=False)    
    registered=u.is_registered()
    if not registered:
        flash("IsardVDI hasn't been registered yet.","error")
    return render_template('admin/pages/updates.html', title="Updates", nav="Updates", registered=registered, connected=True)
            
@app.route('/admin/updates/<kind>', methods=['GET'])
@login_required
@isAdmin
def admin_updates_json(kind):
    return json.dumps(u.getNewKind(kind,current_user.id))

@app.route('/admin/updates/<action>/<kind>', methods=['POST'])
@app.route('/admin/updates/<action>/<kind>/<id>', methods=['POST'])
@login_required
@isAdmin
def admin_updates_actions(action,kind,id=False):
    if request.method == 'POST':
        if action == 'download':
            if id is not False:
                # Only one id
                d=u.getNewKindId(kind,current_user.id,id)
                if kind == 'domains':
                    missing_resources=u.get_missing_resources(d,current_user.id)
                    for k,v in missing_resources.items():
                        for resource in v:
                            app.adminapi.insert_or_update_table_dict(k,v)
                if d is not False:
                    if kind == 'domains':
                        d=u.formatDomains([d],current_user)[0]
                    elif kind == 'media':
                        d=u.formatMedias([d],current_user)[0]
                    app.adminapi.insert_or_update_table_dict(kind,d)
            else:
                # No id, do it will all
                data=u.getNewKind(kind,current_user.id)
                data=[d for d in data if d['new'] is True]
                if kind == 'domains': 
                    data=u.formatDomains(data,current_user)
                elif kind == 'media':
                    data=u.formatMedias(data,current_user)
                app.adminapi.insert_or_update_table_dict(kind,data)
        if action == 'abort':
            app.adminapi.update_table_dict(kind,id,{'status':'DownloadAborting'})
        if action == 'delete':
            if kind == 'domains' or kind == 'media':
                app.adminapi.update_table_dict(kind,id,{'status':'Deleting'})
            else:
                app.adminapi.delete_table_key(kind,id)
            
    return json.dumps([])


    
