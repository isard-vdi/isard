# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8
from flask import render_template, Response, request, redirect, url_for, stream_with_context, flash
from webapp import app
from flask_login import login_required, login_user, logout_user, current_user
import time
import json

from ..lib.log import *

import rethinkdb as r
from ..lib.flask_rethink import RethinkDB
db = RethinkDB(app)
db.init_app(app)

from .decorators import ownsid

@app.route('/classroom', methods=['POST','GET'])
@login_required
def classroom():
    if request.method == 'POST':
        None
    hosts=[]
    for i in range(1,30):
        hosts.append({'ip':'10.200.210.'+str(i),'hostname':'f2a-'+str(i)})
    #~ hosts=[{'ip':'10.200.210.1','hostname':'f2a-01'},
            #~ {'ip':'10.200.210.2','hostname':'f2a-02'},
            #~ {'ip':'10.200.210.3','hostname':'f2a-03'},]
    return render_template('pages/classroom.html', nav='Classroom', hosts=hosts)
