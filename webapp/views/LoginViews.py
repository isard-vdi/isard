# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
from flask import render_template, redirect, request, flash, url_for
from webapp import app
from flask_login import login_required, login_user, logout_user, current_user

from ..auth.authentication import *   
from ..lib.log import *                       

@app.route('/login', methods=['POST', 'GET'])
def login():
    if request.method == 'POST':
        if request.form['user'] is '' or request.form['password'] is '':
            flash("Can't leave it blank",'danger')
        else:
            au=auth()
            user=au.check(request.form['user'],request.form['password'])
            if user:
                login_user(user)
                flash('Logged in successfully.','success')
                if user.is_admin:
                        return redirect(url_for('admin'))
                return redirect(url_for('desktops'))
            else:
                flash('Username not found or incorrect password.','warning')
    remote_addr=request.headers['X-Forwarded-For'] if 'X-Forwarded-For' in request.headers else request.remote_addr
    disposables=app.isardapi.show_disposable(remote_addr)
    return render_template('login.html', disposables=disposables if disposables else '')

@app.route('/')
def index():
    try:
        if current_user.is_authenticated:
            if current_user.is_admin:
               return redirect(url_for('admin'))
        else:
            title='Sign in to start'
    except Exception as e:
        print("Something went wrong with username? Exception:",e)
    remote_addr=request.headers['X-Forwarded-For'] if 'X-Forwarded-For' in request.headers else request.remote_addr
    disposables=app.isardapi.show_disposable(remote_addr)
    return render_template('login.html', disposables=disposables if disposables else '')

@app.route('/logout')
@login_required
def logout():
    logout_ram_user(current_user.username)
    logout_user()
    return redirect(url_for('index'))
