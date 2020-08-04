# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

from functools import wraps

from flask import redirect, url_for, render_template
from flask_login import current_user, logout_user

def isAdmin(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if current_user.is_admin:
            return fn(*args, **kwargs)
        logout_user()
        return render_template('login_category.html')
    return decorated_view

def isAdminManager(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if current_user.is_admin or current_user.role == "manager":
            return fn(*args, **kwargs)
        logout_user()
        return render_template('login_category.html', category=False)
    return decorated_view