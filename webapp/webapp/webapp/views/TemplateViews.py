# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8  
from flask import render_template, Response, request, redirect, url_for, stream_with_context
from webapp import app
from flask_login import login_required, login_user, logout_user, current_user
import time
import json

from ..lib.log import *
                                
import rethinkdb as r
from ..lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from .decorators import ownsid, checkRole

@app.route('/isard-admin/templates')
@login_required
@checkRole
def templates():
    return render_template('pages/templates.html', nav="Templates")

@app.route('/isard-admin/template/get/')
@login_required
def templates_get():
	return json.dumps(app.isardapi.get_user_templates(current_user.id)), 200, {'Content-Type': 'application/json'}
