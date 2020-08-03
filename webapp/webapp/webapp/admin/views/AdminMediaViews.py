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

from .decorators import isAdmin, isAdminManager

import tempfile,os

@app.route('/isard-admin/admin/isard-admin/media', methods=['POST','GET'])
@login_required
@isAdminManager
def admin_media():
    return render_template('admin/pages/media.html', nav='Media')


@app.route('/isard-admin/admin/isard-admin/media/localupload', methods=['POST'])
@login_required
@isAdminManager
def admin_media_localupload():
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
        media['url-web']=url+'admin/isard-admin/media/download/'+secure_filename(handler.filename)
        app.adminapi.media_upload(current_user.id,handler,media)
        tempfile.tempdir=None
        return render_template('admin/pages/media.html', nav='Media')

@app.route('/isard-admin/admin/isard-admin/media/download/<filename>', methods=['GET'])
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
