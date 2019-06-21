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
        elif request.form['user'].startswith(' '):
            flash('Username not found or incorrect password.','warning')
        else:
            au=auth()
            user=au.check(request.form['user'],request.form['password'])
            if user:
                if user.auto is not False:
                    app.isardapi.new_domains_auto_user(user.username,user.auto)
                login_user(user)
                flash('Logged in successfully.','success')
                if user.is_admin:
                    return render_template('admin/pages/hypervisors.html', title="Hypervisors", header="Hypervisors", nav="Hypervisors")
                return render_template('pages/desktops.html', title="Desktops", nav="Desktops")
            else:
                flash('Username not found or incorrect password.','warning')
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    disposables=app.isardapi.show_disposable(remote_addr)
    return render_template('login_disposables.html', disposables=disposables if disposables else '')
        
@app.route('/')
def index():
    try:
        if current_user.is_authenticated:
            if current_user.is_admin:
               return render_template('admin/pages/hypervisors.html', title="Hypervisors", header="Hypervisors", nav="Hypervisors")
    except Exception as e:
        exc_type, exc_obj, exc_tb = sys.exc_info()
        fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
        log.error(exc_type, fname, exc_tb.tb_lineno)
        log.error("Something went wrong with username "+current_user.username+" authentication")
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    disposables=app.isardapi.show_disposable(remote_addr)
    return render_template('login_disposables.html', disposables=disposables if disposables else '')

@app.route('/logout')
@login_required
def logout():
    logout_ram_user(current_user.username)
    logout_user()
    remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    disposables=app.isardapi.show_disposable(remote_addr)
    return render_template('login_disposables.html', disposables=disposables if disposables else '')
    
#~ @app.route('/autologin_secret/<secret>/<user>',methods=['GET'])
#~ def autologin(secret,user):
    #~ with app.app_context():
        #~ if r.table('config').get(1).pluck('autologin').run(db.conn)['autologin']['secret'] == secret:
            #~ print('Secret access granted!')

        #~ au=auth()
        #~ user2login=r.table('users').get(user).run(db.conn)
        #~ user=User(user2login)
        #~ if user:
            #~ login_user(user)
            #~ return redirect(url_for('desktops'))
        #~ else:
            #~ return redicrect(url_for('login'))

# ~ @app.route('/voucher_login', methods=['POST', 'GET'])
# ~ def voucher_login():
    # ~ if request.method == 'POST':
        # ~ remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
        # ~ au=auth_voucher()
        # ~ if au.check_voucher(request.form['voucher']):
            # ~ if au.check_user_exists(request.form['email']):
                # ~ au.register_user(request.form['voucher'],request.form['email'],remote_addr)
                # ~ flash('Resetting account. Email with new isard user sent to '+request.form['email']+'. Please check your email','warning')
            # ~ else:
                # ~ au.register_user(request.form['voucher'],request.form['email'],remote_addr)
                # ~ flash('Email with isard user sent to '+request.form['email']+'. Please check your email','success')
        # ~ else:
            # ~ flash('Invalid registration voucher code','danger')
    
    # ~ disposables=False
    # ~ return render_template('login.html', disposables=disposables if disposables else '')

# ~ @app.route('/voucher_validation/<code>', methods=['GET'])
# ~ def voucher_validation(code):
    # ~ remote_addr=request.headers['X-Forwarded-For'].split(',')[0] if 'X-Forwarded-For' in request.headers else request.remote_addr.split(',')[0]
    # ~ au=auth_voucher()
    # ~ valid=False
    # ~ if au.check_validation(code):
        # ~ au.activate_user(code,remote_addr)
        # ~ valid=True
    # ~ return render_template('voucher_validation.html',valid=valid)
