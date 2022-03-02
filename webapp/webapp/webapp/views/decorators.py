# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import logging
from functools import wraps

import rethinkdb as r
from cachetools import TTLCache, cached
from flask import Flask, abort, redirect, render_template, request, url_for
from flask_login import current_user, logout_user

from webapp import app

from ..lib.api_client import ApiClient
from ..lib.flask_rethink import RethinkDB
from .LoginViews import logout

# from ..lib.log import *

_MAINTENANCE_API_ENDPOINT = "maintenance"

db = RethinkDB(app)
db.init_app(app)


def ownsid(fn):
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
        if id.startswith("_" + current_user.id) or (
            current_user.role == "manager" and current_user.category == id.split("-")[1]
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
        if current_user.role == "manager" and current_user.category == id.split("-")[1]:
            return fn(*args, **kwargs)
        with app.app_context():
            domain = r.table("domains").get(id).pluck("id", "tag").run(db.conn)
        if domain != None:
            if domain.get("id", "").startswith("_" + current_user.id):
                return fn(*args, **kwargs)
            if current_user.role == "advanced" and str(
                domain.get("tag", "")
            ).startswith(current_user.id):
                return fn(*args, **kwargs)
        logout_user()
        return render_template("login_category.html", category=False)

    return decorated_view


def checkRole(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if current_user.role == "user":
            return render_template(
                "pages/desktops.html", title="Desktops", nav="Desktops"
            )
        return fn(*args, **kwargs)

    return decorated_view


def isAdvanced(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if current_user.role == "advanced":
            return fn(*args, **kwargs)
        logout_user()
        return render_template("login_category.html", category=False)

    return decorated_view


@cached(TTLCache(maxsize=1, ttl=5))
def _get_maintenance():
    logging.debug("Check api maintenance mode")
    return ApiClient().get(_MAINTENANCE_API_ENDPOINT)


def maintenance(function):
    """Decorator that returns maintenance response if api is in maintenance mode."""

    @wraps(function)
    def wrapper(*args, **kargs):
        if getattr(current_user, "role", None) != "admin":
            if _get_maintenance():
                return render_template("maintenance.html"), 503
        return function(*args, **kargs)

    return wrapper
