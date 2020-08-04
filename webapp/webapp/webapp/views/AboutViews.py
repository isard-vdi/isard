# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
from flask import render_template, redirect, request, flash, url_for
from webapp import app
from flask_login import login_required, login_user, logout_user, current_user
import json
from ..lib.log import *

from ..auth.authentication import * 

@app.route('/isard-admin/about', methods=['GET'])
def about():
    return render_template('pages/about.html', title="About", header="About", nav="About")

