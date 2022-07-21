# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8

import logging as log

from flask import flash, render_template, request
from flask_login import login_required

from webapp import app

from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()

from ...lib.isardUpdates import Updates

u = Updates()

from .decorators import isAdmin


@app.route("/isard-admin/admin/updates", methods=["GET"])
@login_required
@isAdmin
def admin_updates():
    if not u.is_conected():
        flash(
            "There is a network or update server error at the moment. Try again later.",
            "error",
        )
        return render_template(
            "admin/pages/updates.html",
            title="Downloads",
            nav="Downloads",
            registered=False,
            connected=False,
        )
    registered = u.is_registered()
    if not registered:
        flash("IsardVDI hasn't been registered yet.", "error")
    return render_template(
        "admin/pages/updates.html",
        title="Downloads",
        nav="Downloads",
        registered=registered,
        connected=True,
    )


@app.route("/isard-admin/admin/updates_register", methods=["POST"])
@login_required
@isAdmin
def admin_updates_register():
    if request.method == "POST":
        try:
            if not u.is_registered():
                u.register()
        except Exception as e:
            log.error("Error registering client: " + str(e))
    if not u.is_conected():
        flash(
            "There is a network or update server error at the moment. Try again later.",
            "error",
        )
        return render_template(
            "admin/pages/updates.html",
            title="Downloads",
            nav="Downloads",
            registered=False,
            connected=False,
        )
    registered = u.is_registered()
    if not registered:
        flash("IsardVDI hasn't been registered yet.", "error")
    return render_template(
        "admin/pages/updates.html",
        title="Downloads",
        nav="Downloads",
        registered=registered,
        connected=True,
    )


@app.route("/isard-admin/admin/updates_reload", methods=["POST"])
@login_required
@isAdmin
def admin_updates_reload():
    if request.method == "POST":
        u.reload_updates()
    if not u.is_conected():
        flash(
            "There is a network or update server error at the moment. Try again later.",
            "error",
        )
        return render_template(
            "admin/pages/updates.html",
            title="Downloads",
            nav="Downloads",
            registered=False,
            connected=False,
        )
    registered = u.is_registered()
    if not registered:
        flash("IsardVDI hasn't been registered yet.", "error")
    return render_template(
        "admin/pages/updates.html",
        title="Downloads",
        nav="Downloads",
        registered=registered,
        connected=True,
    )
