# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

from functools import wraps

import rethinkdb as r
from flask import render_template, request
from flask_login import current_user, logout_user

from webapp import app

from ...lib.flask_rethink import RethinkDB

db = RethinkDB(app)
db.init_app(app)


def isAdmin(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if current_user.is_admin:
            return fn(*args, **kwargs)
        logout_user()
        return render_template("login_category.html")

    return decorated_view


def isAdminManager(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if current_user.is_admin or current_user.role == "manager":
            return fn(*args, **kwargs)
        logout_user()
        return render_template("login_category.html", category=False)

    return decorated_view


def isAdvanced(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if current_user.role == "advanced":
            return fn(*args, **kwargs)
        logout_user()
        return render_template("login_category.html", category=False)

    return decorated_view


def isAdminManagerAdvanced(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if (
            current_user.is_admin
            or current_user.role == "manager"
            or current_user.role == "advanced"
        ):
            return fn(*args, **kwargs)
        logout_user()
        return render_template("login_category.html", category=False)

    return decorated_view


def ownsidortag(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if current_user.role == "admin":
            return fn(*args, **kwargs)
        try:
            myargs = request.get_json(force=True)
        except:
            myargs = request.form.to_dict()
        try:
            id = kwargs["id"]
        except:
            try:
                id = myargs["pk"]
            except:
                id = myargs["id"]
        with app.app_context():
            category = r.table("users").get(id)["category"].run(db.conn)
        if current_user.role == "manager" and current_user.category == category:
            return fn(*args, **kwargs)
        if current_user.role == "advanced":
            with app.app_context():
                if str(
                    r.table("domains")
                    .get(id)
                    .pluck("tag")
                    .run(db.conn)
                    .get("tag", False)
                ).startswith(current_user.id):
                    return fn(*args, **kwargs)
        logout_user()
        return render_template("login_category.html", category=False)

    return decorated_view
