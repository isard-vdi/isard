# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json

from flask import render_template, request, redirect, url_for, flash
from flask_login import login_required

from webapp import app
from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

from .decorators import isAdmin
'''
USERS
'''

from ...auth.authentication import * 
@app.route('/admin/users', methods=['POST','GET'])
@login_required
@isAdmin
def admin_users():
    # ~ res=True
    # ~ if request.method == 'POST':
        # ~ create_dict=app.isardapi.f.unflatten_dict(request.form)
        # ~ create_dict.pop('password2', None)
        # ~ create_dict['kind']='local'
        # ~ import pprint
        # ~ pprint.pprint(create_dict)
        # ~ if res is True:
            # ~ flash('Hypervisor '+create_dict['id']+' added to the system.','success')
            # ~ return redirect(url_for('admin_users'))
        # ~ else:
            # ~ flash('Could not create user. Maybe you have one with the same name?','danger')
            # ~ return redirect(url_for('admin_users'))
   
    return render_template('admin/pages/users.html', nav="Users")


@app.route('/admin/users/get/')
@login_required
@isAdmin
def admin_users_get():
    return json.dumps(app.adminapi.get_admin_users_domains()), 200, {'ContentType': 'application/json'}
    #~ return json.dumps(app.adminapi.get_admin_user()), 200, {'ContentType': 'application/json'}

@app.route('/admin/users/detail/<id>')
@login_required
@isAdmin
def admin_users_get_detail(id):
    data = 'user desktops'
    return json.dumps(data), 200, {'ContentType':'application/json'} 

@app.route('/admin/userschema', methods=['POST'])
@login_required
@isAdmin
def admin_userschema():
    dict={}
    dict['role']=app.adminapi.get_admin_table('roles', ['id', 'name', 'description'])
    dict['category']=app.adminapi.get_admin_table('categories', ['id', 'name', 'description'])
    dict['group']=app.adminapi.get_admin_table('groups', ['id', 'name', 'description'])
    return json.dumps(dict)

@app.route('/admin/user/delete', methods=['POST'])
@login_required
@isAdmin
def admin_user_delete(doit=False):
    try:
        args = request.get_json(force=True)
    except:
        args = request.form.to_dict()
    return json.dumps(app.adminapi.user_delete_checks(args['pk']))
        
@app.route('/admin/users/update', methods=['POST'])
@login_required
@isAdmin
def admin_users_update_update():
    if request.method == 'POST':
        try:
            args = request.get_json(force=True)
        except:
            args = request.form.to_dict()
        try:
            if float(app.isardapi.get_user_quotas(current_user.username)['rqp']) >= 100:
                 return json.dumps('Quota for starting domains full.'), 500, {'ContentType':'application/json'}
            if app.isardapi.update_table_value('domains', args['pk'], args['name'], args['value']):
                return json.dumps('Updated'), 200, {'ContentType':'application/json'}
            else:
                return json.dumps('This is not a valid value.'), 500, {'ContentType':'application/json'}
        except Exception as e:
            return json.dumps('Wrong parameters.'), 500, {'ContentType':'application/json'}



@app.route('/admin/users/nonexists', methods=['POST'])
@login_required
@isAdmin
def admin_users_nonexists():
    if request.method == 'POST':
        try:
            args = request.get_json(force=True)
        except:
            args = request.form.to_dict()
        try:
            au=auth()
            data = au.ldap_users_exists()['nonvalid']
            if 'commit' in args.keys() and args['commit']:
                for u in data:
                    app.adminapi.user_toggle_active(u['id'])
            return json.dumps(data), 200, {'ContentType':'application/json'}
        except Exception as e:
            #~ print(e)
            return json.dumps('Wrong parameters.'), 500, {'ContentType':'application/json'}
