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

import os
from ..auth.authentication import * 

@app.route('/isard-admin/about', methods=['GET'])
def about():
    with open("/version", "r") as file:
        version = file.read()
    with open("/version_link", "r") as file:
        version_link = file.read()
    return render_template(
        "pages/about.html",
        title="About",
        header="About",
        nav="About",
        version=version,
        version_link=version_link,
    )
