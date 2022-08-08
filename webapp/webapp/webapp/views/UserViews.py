# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
from flask import flash, jsonify, make_response, redirect, render_template, request
from flask_login import current_user, login_required, login_user, logout_user

from webapp import app

from ..auth.authentication import *
from ..lib.log import *
from .decorators import checkRole, maintenance


@app.route("/isard-admin/about", methods=["GET"])
@maintenance
def about():
    return render_template(
        "pages/about.html",
        title="About",
        header="About",
        nav="About",
    )


@app.route("/isard-admin/healthcheck", methods=["GET"])
def healthcheck():
    return ""


"""
LANDING PAGE
"""


@app.route("/isard-admin/desktops")
@login_required
@maintenance
def desktops():
    return render_template("pages/desktops.html", title="Desktops", nav="Desktops")


"""
TEMPLATES PAGE
"""


@app.route("/isard-admin/templates")
@login_required
@maintenance
@checkRole
def templates():
    return render_template("pages/templates.html", nav="Templates")


"""
MEDIA PAGE
"""


@app.route("/isard-admin/media", methods=["GET"])
@login_required
@maintenance
def media():
    return render_template("pages/media.html", nav="Media")


@app.route("/isard-admin", methods=["POST", "GET"])
def redirect_to_login():
    return redirect("/")


"""
LOGIN PAGE
"""


@app.route("/isard-admin/login", methods=["POST", "GET"])
@app.route("/isard-admin/login/<category>", methods=["POST", "GET"])
def login(category="default"):
    user = get_authenticated_user()
    if user:
        login_user(user)
        flash("Authenticated via backend.", "success")
        return render_template("pages/desktops.html", title="Desktops", nav="Desktops")
    return redirect("/login")


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
                        localStorage.removeItem('token');
                        window.location = '{login_path}';
                    </script>
                </body>
            </html>
        """
    )
    remote_logout()
    return response
