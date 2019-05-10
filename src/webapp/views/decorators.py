# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

from functools import wraps
from flask import Flask, abort, redirect, url_for, request
from flask_login import current_user

from .LoginViews import logout
from webapp import app
import json

def ownsid(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if current_user.role == 'admin': return fn(*args, **kwargs)
        try:
            myargs = request.get_json(force=True)
        except:
            myargs = request.form.to_dict()
        try:
            id = kwargs['id']
        except:
            try:
                id = myargs['pk']
            except:
                id = myargs['id']
            
        if id.startswith('_'+current_user.id+'_'):
            return fn(*args, **kwargs)
        return render_template('login_disposables.html', disposables='')
    return decorated_view

def checkRole(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if current_user.role == 'user': return render_template('pages/desktops.html', title="Desktops", nav="Desktops")
        return fn(*args, **kwargs)
    return decorated_view
