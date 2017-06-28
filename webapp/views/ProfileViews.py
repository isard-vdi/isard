# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
from flask import render_template, redirect, request, flash, url_for
from webapp import app
from flask_login import login_required, login_user, logout_user, current_user

#~ from ..auth.authentication import *   
from ..lib.log import *                       

@app.route('/profile', methods=['POST', 'GET'])
@login_required
def profile():
    if request.method == 'POST':
        None
    user=app.isardapi.get_user(current_user.username)
    return render_template('pages/user_profile.html',user=user)

@app.route('/profile_pwd', methods=['POST'])
@login_required
def profile_pwd():
    if request.method == 'POST':
        
        app.isardapi.update_user_password(current_user.id,request.form['password'])
    user=app.isardapi.get_user(current_user.username)
    return render_template('pages/user_profile.html',user=user)
