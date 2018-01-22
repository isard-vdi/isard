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


@app.route('/admin/users/get')
@login_required
@isAdmin
def admin_users_get():
    return json.dumps(app.adminapi.get_admin_users_domains()), 200, {'ContentType': 'application/json'}
    #~ return json.dumps(app.adminapi.get_admin_user()), 200, {'ContentType': 'application/json'}

@app.route('/admin/users/detail/<id>')
@login_required
@isAdmin
def adminUsersGetDetail(id):
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
    

import csv
@app.route('/admin/users/csv/import', methods=['POST','GET'])
@login_required
@isAdmin
def admin_users_csv_import():
    res=True
    if request.method == 'POST':
        fieldnames = ('role','category','password',
                      'quota-domains-templates','active','quota-domains-running',
                      'quota-hardware-memory', 'id', 'quota-hardware-vcpus',
                      'group', 'quota-domains-desktops_disk_max', 'quota-domains-isos',
                      'mail', 'quota-domains-isos_disk_max', 'kind',
                      'quota-domains-desktops', 'name', 'quota-domains-templates_disk_max')
        imported_users=[]
        reader = csv.DictReader( request.form, fieldnames)
        for row in reader:
            imported_users.append(json.dumps(app.isardapi.f.unflatten_dict(row)))
        
        if res is True:
            flash('Imported')
            return redirect(url_for('admin_users_csv_import'))
        else:
            flash('Something wrong in import.','danger')
            return redirect(url_for('admin_users_csv_import'))

    return render_template('admin/pages/users_import_csv.html', nav="Users")
