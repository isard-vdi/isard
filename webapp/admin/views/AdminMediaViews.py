# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json

from flask import render_template, Response, request, redirect, url_for
from flask import after_this_request
from flask_login import login_required, login_user, logout_user, current_user

from werkzeug import secure_filename

from webapp import app
from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

from .decorators import isAdmin

import tempfile,os

@app.route('/admin/media', methods=['POST','GET'])
@login_required
@isAdmin
def admin_media():
    #~ if request.method == 'POST':
        #~ hp=request.form['hypervisors_pools']
        #~ url=request.form['url']
        #~ filename=url.split('/')[-1]
        #~ iso=app.isardapi.user_relative_disk_path(current_user.username, filename)
        #~ if not iso:
            #~ flash('Something went wrong, filename has extrange characters','danger')
            #~ return render_template('pages/isos.html', nav='Isos')
        #~ iso['status']='Starting'
        #~ iso['name']=request.form['name']
        #~ iso['percentage']=0
        #~ iso['url']=url
        #~ iso['hypervisor_pool']=hp
        #~ iso['user']=current_user.username
        #~ if not app.isardapi.add_dict2table(iso,'isos'):
            #~ flash('Something went wrong. Upload task not scheduled')
        #~ return redirect(url_for('admin_media_upload'))
    return render_template('admin/pages/media.html', nav='Media')


@app.route('/admin/media/localupload', methods=['POST'])
@login_required
@isAdmin
def admin_media_localupload():
        # ~ print(tempfile.tempdir)
        tempfile.tempdir='/var/tmp'
        media={}
        media['name']=request.form['name']
        media['kind']=request.form['kind']
        media['description']=request.form['description']
        media['hypervisors_pools']=[request.form['hypervisors_pools']]
        media['allowed']=json.loads(request.form['allowed'])
        # Only one can be uploaded!

        for f in request.files:
            handler=request.files[f]

        if app.adminapi.check_socket('isard-hypervisor',22):
            # It is a docker!
            url='http://isard-webapp:5000/'
        else:
            if '5000' not in request.url_root:
                url='https://'+request.url_root.split('http://')[1]
            else:
                url=request.url_root
        media['url-web']=url+'admin/media/download/'+secure_filename(handler.filename)
        app.adminapi.media_upload(current_user.username,handler,media)
        tempfile.tempdir=None
        return render_template('admin/pages/media.html', nav='Media')

@app.route('/admin/media/download/<filename>', methods=['GET'])
#~ @login_required
#~ @isAdmin
def admin_media_download(filename):
    with open('./uploads/'+filename, 'rb') as isard_file:
        data=isard_file.read()  

    @after_this_request
    def remove_file(response):
        try:
            os.remove('./uploads/'+filename)
        except Exception as error:
            print("Error removing or closing downloaded file handle", error)
        return response
                  
    return Response( data,
        mimetype="application/octet-stream",
        headers={"Content-Disposition":"attachment;filename="+filename})
