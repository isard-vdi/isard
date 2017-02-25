# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
from flask import render_template, redirect, request, flash, url_for
from webapp import app
from flask_login import login_required, login_user, logout_user, current_user
import json
from ..lib.log import *

from ..auth.authentication import * 

@app.route('/about', methods=['GET','POST'])
def about():
    if request.method == 'POST':
        data = request.get_json(force=True)
        au=auth()
        user=au.fakecheck(data['username'],data['password'])
        if user:
            log.info(user.role)
            logout_user()
            login_user(user)
            return json.dumps('User changed.'), 200, {'ContentType':'application/json'}
        return json.dumps('Not allowed.'), 500, {'ContentType':'application/json'}
    return render_template('pages/about.html', title="About", header="About", nav="About")


@app.route('/about/post', methods=['POST'])
def about_post():
        return json.dumps('User changed.'), 200, {'ContentType':'application/json'}
