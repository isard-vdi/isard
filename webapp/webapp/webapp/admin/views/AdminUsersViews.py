# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json

from flask import render_template, request, redirect, url_for, flash
from flask_login import current_user,login_required

from webapp import app
from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

from .decorators import isAdmin, isAdminManager
'''
USERS
'''

from ...auth.authentication import * 
@app.route('/isard-admin/admin/users', methods=['POST','GET'])
@login_required
@isAdminManager
def admin_users():
    return render_template('admin/pages/users.html', nav="Users")


@app.route('/isard-admin/admin/users/get/')
@login_required
@isAdminManager
def admin_users_get():
    data = app.adminapi.get_admin_users_domains()
    if current_user.role == 'manager':
        data = [d for d in data if d['category'] == current_user.category]
    return json.dumps(data), 200, {'Content-Type': 'application/json'}

@app.route('/isard-admin/admin/group/enrollment/<id>')
@login_required
@isAdminManager
def admin_group_enrollment(id):
    data = app.adminapi.get_group(id)
    if current_user.role == 'manager' and data != {}:
        if data['parent_category'] != current_user.category: return json.dumps({}), 500, {'Content-Type': 'application/json'}  
    return json.dumps(data), 200, {'Content-Type': 'application/json'}

@app.route('/isard-admin/admin/group/enrollment_reset/<id>/<role>')
@login_required
@isAdminManager
def admin_group_enrollment_reset(id,role):
    data = app.adminapi.get_group(id)
    if current_user.role == 'manager' and data != {}:
        if data['parent_category'] != current_user.category: return json.dumps({}), 500, {'Content-Type': 'application/json'}  
    data = app.adminapi.enrollment_reset(id,role)
    return json.dumps(data), 200, {'Content-Type': 'application/json'}

@app.route('/isard-admin/admin/group/enrollment_disable/<id>/<role>')
@login_required
@isAdminManager
def admin_group_enrollment_disable(id,role):
    data = app.adminapi.get_group(id)
    if current_user.role == 'manager' and data != {}:
        if data['parent_category'] != current_user.category: return json.dumps({}), 500, {'Content-Type': 'application/json'}  
    data = app.adminapi.enrollment_reset(id,role,disabled=True)
    return json.dumps(data), 200, {'Content-Type': 'application/json'}

@app.route('/isard-admin/admin/users/detail/<id>')
@login_required
@isAdminManager
def admin_users_get_detail(id):
    data = 'user desktops'
    return json.dumps(data), 200, {'Content-Type':'application/json'} 

@app.route('/isard-admin/admin/userschema', methods=['POST'])
@login_required
@isAdminManager
def admin_userschema():
    dict={}
    dict['role']=app.adminapi.get_admin_table('roles', pluck=['id', 'name', 'description'], order ='name')
    if current_user.role == 'manager':
        dict['role'] = [r for r in dict['role'] if r['id'] in ['manager', 'advanced', 'user']]

    dict['category']=app.adminapi.get_admin_table('categories', pluck=['id', 'name', 'description'], order ='name')
    if current_user.role == 'manager':
        dict['category'] = [c for c in dict['category'] if c['id'] == current_user.category] 

    dict['group']=app.adminapi.get_admin_table('groups', pluck=['id', 'name', 'description','parent_category'], order = 'name')
    if current_user.role == 'manager':
        dict['group'] = [g for g in dict['group'] if 'parent_category' in g.keys() and g['parent_category'] == current_user.category] 
    else:
        for g in dict['group']:
            if 'parent_category' in g.keys(): g['name']='['+g['parent_category']+'] '+g['name']
    return json.dumps(dict)

@app.route('/isard-admin/admin/user/delete', methods=['POST'])
@login_required
@isAdminManager
def admin_user_delete(doit=False):
    try:
        args = request.get_json(force=True)
    except:
        args = request.form.to_dict()
    return json.dumps(app.adminapi.user_delete_checks(args['pk']))

@app.route('/isard-admin/admin/category/delete', methods=['POST'])
@login_required
@isAdminManager
def admin_category_delete(doit=False):
    try:
        args = request.get_json(force=True)
    except:
        args = request.form.to_dict()
    return json.dumps(app.adminapi.category_delete_checks(args['pk']))

@app.route('/isard-admin/admin/group/delete', methods=['POST'])
@login_required
@isAdminManager
def admin_group_delete(doit=False):
    try:
        args = request.get_json(force=True)
    except:
        args = request.form.to_dict()
    return json.dumps(app.adminapi.group_delete_checks(args['pk']))

