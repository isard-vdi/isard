# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

import json
import os

#!flask/bin/python
# coding=utf-8
from flask import flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user

from webapp import app

from ..auth.authentication import *
from ..lib.log import *


@app.route("/isard-admin/about", methods=["GET"])
def about():
    return render_template(
        "pages/about.html",
        title="About",
        header="About",
        nav="About",
    )
