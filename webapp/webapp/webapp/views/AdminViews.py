# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!flask/bin/python
# coding=utf-8
import json
import logging as log

from flask import flash, jsonify, make_response, redirect, render_template, request
from flask_login import current_user, login_required, login_user, logout_user

from webapp import app

from ..auth.authentication import *
from ..lib import admin_api

app.adminapi = admin_api.isardAdmin()

from ..lib.isardUpdates import Updates
from ..lib.log import *
from .decorators import isAdmin, isAdminManager, maintenance

u = Updates()


@app.route("/isard-admin/about", methods=["GET"])
@maintenance
def about():
    return render_template(
        "pages/about.html",
        title="About",
        header="About",
        nav="About",
    )


@app.route("/isard-admin/healthcheck", methods=["GET"])
def healthcheck():
    return ""


"""
LOGIN PAGE
"""


@app.route("/isard-admin/login", methods=["POST", "GET"])
@app.route("/isard-admin/login/<category>", methods=["POST", "GET"])
def login(category="default"):
    user = get_authenticated_user()
    if user:
        login_user(user)
        flash("Authenticated via backend.", "success")
        return render_template(
            "admin/pages/domains.html",
            title="Desktops",
            nav="Desktops",
            icon="desktops",
        )
    return redirect("/login")


@app.route("/isard-admin/logout/remote")
def remote_logout():
    try:
        logout_ram_user(current_user.id)
    except:
        # The user does not exist already
        None
    logout_user()
    return jsonify(success=True)


@app.route("/isard-admin/logout")
@login_required
def logout():
    login_path = app.isardapi.__class__.get_login_path()
    response = make_response(
        f"""
            <!DOCTYPE html>
            <html>
                <body>
                    <script>
                        localStorage.removeItem('token');
                        window.location = '{login_path}';
                    </script>
                </body>
            </html>
        """
    )
    remote_logout()
    return response


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
        icon = "cubes"
    if nav == "Storage":
        icon = "folder-open"
        return render_template(
            "admin/pages/storage.html", title=nav, nav=nav, icon=icon
        )
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
    if nav == "BookablesEvents":
        icon = "history"
        return render_template(
            "admin/pages/bookables_events.html", title=nav, nav=nav, icon=icon
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
    return render_template("admin/pages/media.html", nav="Media", title="Media")


"""
USERS
"""


@app.route("/isard-admin/admin/users/<nav>", methods=["POST", "GET"])
@login_required
@isAdminManager
def admin_users(nav):
    if nav == "Management":
        return render_template(
            "admin/pages/users_management.html",
            nav=nav,
            title="Management",
        )
    elif nav == "QuotasLimits":
        return render_template(
            "admin/pages/users_quotas_limits.html",
            nav=nav,
            title="Quotas / Limits",
        )


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


@app.route("/isard-admin/admin/storage_nodes", methods=["GET"])
@login_required
@isAdmin
def storage_nodes():
    """
    Storage Nodes
    """
    return render_template(
        "admin/pages/storage_nodes.html",
        title="Storage Nodes",
        nav="Storage Nodes",
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
    return render_template("admin/pages/config.html", nav="Config", title="Config")


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
