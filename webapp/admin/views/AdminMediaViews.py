# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json

from flask import render_template, Response, request, redirect, url_for
from flask_login import login_required

from webapp import app
from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

import rethinkdb as r
from ...lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from .decorators import isAdmin

@app.route('/admin/media', methods=['POST','GET'])
def admin_media():
    if request.method == 'POST':
        hp=request.form['hypervisors_pools']
        url=request.form['url']
        filename=url.split('/')[-1]
        iso=app.isardapi.user_relative_disk_path(current_user.username, filename)
        if not iso:
            flash('Something went wrong, filename has extrange characters','danger')
            return render_template('pages/isos.html', nav='Isos')
        iso['status']='Starting'
        iso['name']=request.form['name']
        iso['percentage']=0
        iso['url']=url
        iso['hypervisor_pool']=hp
        iso['user']=current_user.username
        if not app.isardapi.add_dict2table(iso,'isos'):
            flash('Something went wrong. Upload task not scheduled')
        return redirect(url_for('admin_media_upload'))
    return render_template('admin/pages/media.html', nav='Isos')
