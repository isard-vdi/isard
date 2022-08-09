# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json
import logging as log

from flask import flash, render_template, request
from flask_login import login_required

from webapp import app

from ...lib import admin_api

app.adminapi = admin_api.isardAdmin()


from ...lib.isardUpdates import Updates
from ..decorators import isAdmin, isAdminManager

u = Updates()


"""
LANDING ADMIN PAGE
"""


@app.route("/isard-admin/admin")
@login_required
@isAdmin
def admin():
    return render_template(
        "admin/pages/hypervisors.html",
        title="Hypervisors",
        header="Hypervisors",
        nav="Hypervisors",
    )


"""
DOMAINS PAGES
"""


@app.route("/isard-admin/admin/domains/render/<nav>")
@login_required
@isAdminManager
def admin_domains(nav="Domains"):
    icon = ""
    if nav == "Desktops":
        icon = "desktop"
    if nav == "Templates":
        icon = "cube"
    if nav == "Bases":
        icon = "cubes"
    if nav == "Resources":
        icon = "arrows-alt"
        return render_template(
            "admin/pages/domains_resources.html", title=nav, nav=nav, icon=icon
        )
    if nav == "Bookables":
        icon = "briefcase"
        return render_template(
            "admin/pages/bookables.html", title=nav, nav=nav, icon=icon
        )
    if nav == "Priority":
        icon = "briefcase"
        return render_template(
            "admin/pages/bookables_priority.html", title=nav, nav=nav, icon=icon
        )
    else:
        return render_template(
            "admin/pages/domains.html", title=nav, nav=nav, icon=icon
        )


"""
MEDIA
"""


@app.route("/isard-admin/admin/isard-admin/media", methods=["POST", "GET"])
@login_required
@isAdminManager
def admin_media():
    return render_template("admin/pages/media.html", nav="Media")


"""
USERS
"""


@app.route("/isard-admin/admin/users", methods=["POST", "GET"])
@login_required
@isAdminManager
def admin_users():
    return render_template("admin/pages/users.html", nav="Users")


"""
HYPERVISORS
"""


@app.route("/isard-admin/admin/hypervisors", methods=["GET"])
@login_required
@isAdmin
def admin_hypervisors():
    return render_template(
        "admin/pages/hypervisors.html",
        title="Hypervisors",
        header="Hypervisors",
        nav="Hypervisors",
    )


"""
UPDATES
"""


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


"""
CONFIG
"""


@app.route("/isard-admin/admin/config", methods=["GET", "POST"])
@login_required
@isAdminManager
def admin_config():
    if request.method == "POST":
        return (
            json.dumps(app.adminapi.get_admin_config(1)),
            200,
            {"Content-Type": "application/json"},
        )
    return render_template("admin/pages/config.html", nav="Config")


"""
BACKUP & RESTORE
"""


@app.route("/isard-admin/admin/backup/upload", methods=["POST"])
@login_required
@isAdmin
def admin_backup_upload():
    for f in request.files:
        app.adminapi.upload_backup(request.files[f])
    return json.dumps("Updated"), 200, {"Content-Type": "application/json"}
