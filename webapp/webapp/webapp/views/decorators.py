# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import logging
from functools import wraps

from cachetools import TTLCache, cached
from flask import render_template
from flask_login import current_user, logout_user

from webapp import app

from ..lib.api_client import ApiClient
from ..lib.flask_rethink import RethinkDB

_MAINTENANCE_API_ENDPOINT = "maintenance"

db = RethinkDB(app)
db.init_app(app)


def checkRole(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if current_user.role == "user":
            return render_template(
                "pages/desktops.html", title="Desktops", nav="Desktops"
            )
        return fn(*args, **kwargs)

    return decorated_view


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
