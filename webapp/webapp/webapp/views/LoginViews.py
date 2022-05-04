# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import requests

#!flask/bin/python
# coding=utf-8
from flask import (
    flash,
    jsonify,
    make_response,
    redirect,
    render_template,
    request,
    url_for,
)
from flask_login import current_user, login_required, login_user, logout_user

from webapp import app

from ..auth.authentication import *
from ..lib.log import *

""" @app.route('/isard-admin/admin', methods=['POST', 'GET'])
def login():
    if request.method == 'POST':
        if request.form['user'] == '' or request.form['password'] == '':
            flash("Can't leave it blank",'danger')
        elif request.form['user'].startswith(' '):
            flash('Username not found or incorrect password.','warning')
        else:
            au=auth()
            user=au.check(request.form['user'],request.form['password'])
            if user:
                if user.auto != False:
                    app.isardapi.new_domains_auto_user(user.username,user.auto)
                login_user(user)
                flash('Logged in successfully.','success')
                if user.is_admin:
                    return render_template('admin/pages/hypervisors.html', title="Hypervisors", header="Hypervisors", nav="Hypervisors")
                return render_template('pages/desktops.html', title="Desktops", nav="Desktops")
            else:
                flash('Username not found or incorrect password.','warning')
    return render_template('login.html') """


@app.route("/isard-admin", methods=["POST", "GET"])
def redirect_to_login():
    return redirect("/")


@app.route("/isard-admin/login", methods=["POST", "GET"])
@app.route("/isard-admin/login/<category>", methods=["POST", "GET"])
def login(category="default"):
    if request.method == "POST":
        if request.form["user"] == "" or request.form["password"] == "":
            flash("Can't leave it blank", "danger")
        elif request.form["user"].startswith(" "):
            flash("Username not found or incorrect password.", "warning")
        else:
            au = auth()
            if "category" in request.form:
                id = (
                    "local-"
                    + request.form["category"]
                    + "-"
                    + request.form["user"]
                    + "-"
                    + request.form["user"]
                )
            user = au.check(id, request.form["password"])
            if user:
                if user.auto != False:
                    app.isardapi.new_domains_auto_user(user.id, user.auto)
                login_user(user)
                flash("Logged in successfully.", "success")
                return render_template(
                    "pages/desktops.html", title="Desktops", nav="Desktops"
                )
            else:
                flash("Username not found or incorrect password.", "warning")
    user = get_authenticated_user()
    if user:
        login_user(user)
        flash("Authenticated via backend.", "success")
        return render_template("pages/desktops.html", title="Desktops", nav="Desktops")
    category = app.isardapi.get_category(category)
    if category != False:
        return render_template("login_category.html", category=category)
    return render_template("login_category.html", category=False)


@app.route("/isard-admin/logout/remote")
def remote_logout():
    try:
        logout_ram_user(current_user.id)
    except:
        # The user does not exist already
        None
    logout_user()
    return jsonify(success=True)


@app.route("/isard-admin/logout")
@login_required
def logout():
    login_path = app.isardapi.__class__.get_login_path()
    response = make_response(
        f"""
            <!DOCTYPE html>
            <html>
                <body>
                    <script>
                        sessionStorage.removeItem('token');
                        window.location = '{login_path}';
                    </script>
                </body>
            </html>
        """
    )
    remote_logout()
    return response
