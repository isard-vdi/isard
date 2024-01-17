#
#   Copyright © 2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import os

from flask import flash, jsonify, make_response, redirect, render_template
from flask_login import current_user, login_required, login_user, logout_user

from webapp import app

from ..auth.authentication import *
from ..lib.log import *
from .decorators import isAdmin, isAdminManager, maintenance

monitor_host = os.getenv("GRAFANA_WEBAPP_URL")
if not monitor_host:
    monitor_host = f'https://{os.getenv("DOMAIN", "localhost")}/monitor'


@app.route("/isard-admin/admin/landing", methods=["GET"])
@login_required
@maintenance
def admin_landing():
    if current_user.is_admin:
        return render_template(
            "admin/pages/hypervisors.html",
            title="Hypervisors",
            header="Hypervisors",
            nav="Hypervisors",
            monitor_host=monitor_host,
        )
    if current_user.role == "manager":
        return render_template(
            "admin/pages/analytics.html", nav="Analytics", title="Analytics"
        )


@app.route("/isard-admin/about", methods=["GET"])
@maintenance
def about():
    return render_template(
        "pages/about.html",
        title="About",
        header="About",
        nav="About",
        monitor_host=monitor_host,
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
            "admin/pages/desktops.html",
            title="Desktops",
            nav="Desktops",
            icon="desktops",
            monitor_host=monitor_host,
        )
    return redirect("/login")


@app.route("/isard-admin/logout/remote")
def remote_logout():
    logout_user()
    return jsonify(success=True)


@app.route("/isard-admin/logout")
@login_required
def logout():
    response = requests.get(
        f"http://isard-api:5000/api/v3/category/{current_user.category}/custom_url"
    )
    if response.status_code == 200:
        login_path = response.text
    else:
        login_path = "/login"
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
        monitor_host=monitor_host,
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
        return render_template(
            "admin/pages/desktops.html",
            title=nav,
            nav=nav,
            icon=icon,
            monitor_host=monitor_host,
        )
    if nav == "Templates":
        icon = "cubes"
        return render_template(
            "admin/pages/templates.html",
            title=nav,
            nav=nav,
            icon=icon,
            monitor_host=monitor_host,
        )
    if nav == "Deployments":
        icon = "tv"
        return render_template(
            "admin/pages/deployments.html",
            title=nav,
            nav=nav,
            icon=icon,
            monitor_host=monitor_host,
        )
    if nav == "Storage":
        icon = "folder-open"
        return render_template(
            "admin/pages/storage.html",
            title=nav,
            nav=nav,
            icon=icon,
            monitor_host=monitor_host,
        )
    if nav == "Bases":
        icon = "cubes"
    if nav == "Resources":
        icon = "arrows-alt"
        return render_template(
            "admin/pages/domains_resources.html",
            title=nav,
            nav=nav,
            icon=icon,
            monitor_host=monitor_host,
        )
    if nav == "Bookables":
        icon = "briefcase"
        return render_template(
            "admin/pages/bookables.html",
            title=nav,
            nav=nav,
            icon=icon,
            monitor_host=monitor_host,
        )
    if nav == "BookablesEvents":
        icon = "history"
        return render_template(
            "admin/pages/bookables_events.html",
            title=nav,
            nav=nav,
            icon=icon,
            monitor_host=monitor_host,
        )
    if nav == "Priority":
        icon = "briefcase"
        return render_template(
            "admin/pages/bookables_priority.html",
            title=nav,
            nav=nav,
            icon=icon,
            monitor_host=monitor_host,
        )
    if nav == "Recyclebin":
        icon = "trash"
        return render_template(
            "admin/pages/recyclebin.html", title=nav, nav=nav, icon=icon
        )

    return render_template(
        "admin/pages/desktops.html",
        title=nav,
        nav=nav,
        icon=icon,
        monitor_host=monitor_host,
    )


@app.route("/isard-admin/admin/domains/render/Recyclebin/<nav>")
@login_required
@isAdminManager
def admin_recyclebin(nav="Disks"):
    if nav == "Domains":
        icon = "dektop"
        return render_template(
            "admin/pages/recyclebin_domains.html", title=nav, nav=nav, icon=icon
        )


@app.route("/isard-admin/admin/domains/render/status")
@login_required
@isAdmin
def admin_desktops_status(nav="Desktops Status"):
    icon = "dektop"
    return render_template(
        "admin/pages/desktops_status.html", title=nav, nav=nav, icon=icon
    )


"""
MEDIA
"""


@app.route("/isard-admin/admin/isard-admin/media", methods=["POST", "GET"])
@login_required
@isAdminManager
def admin_media():
    return render_template(
        "admin/pages/media.html",
        nav="Media",
        title="Media",
        monitor_host=monitor_host,
    )


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
            monitor_host=monitor_host,
        )
    elif nav == "QuotasLimits":
        return render_template(
            "admin/pages/users_quotas_limits.html",
            nav=nav,
            title="Quotas / Limits",
            monitor_host=monitor_host,
        )


@app.route("/isard-admin/admin/users/UserStorage", methods=["POST", "GET"])
@login_required
@isAdmin
def admin_users_user_storage():
    return render_template(
        "admin/pages/user_storage.html",
        nav="UserStorage",
        title="User Storage",
        monitor_host=monitor_host,
    )


@app.route("/isard-admin/admin/users/authentication", methods=["POST", "GET"])
@login_required
@isAdmin
def admin_users_authentication():
    return render_template(
        "admin/pages/authentication.html",
        nav="authentication",
        title="Authentication",
        monitor_host=monitor_host,
    )


"""
USAGE
"""


@app.route("/isard-admin/admin/usage", methods=["GET"])
@login_required
@isAdminManager
def admin_usage():
    return render_template(
        "admin/pages/usage.html",
        nav="Usage",
        title="Usage",
        monitor_host=monitor_host,
    )


@app.route("/isard-admin/admin/usage_config", methods=["GET"])
@login_required
@isAdminManager
def admin_usage_config():
    return render_template(
        "admin/pages/usage_config.html",
        nav="Usage config",
        title="Usage config",
        monitor_host=monitor_host,
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
        monitor_host=monitor_host,
    )


@app.route("/isard-admin/admin/queues", methods=["GET"])
@login_required
@isAdmin
def queues():
    """
    Storage Nodes
    """
    return render_template(
        "admin/pages/queues.html",
        title="Queues registeres",
        nav="Queues",
        monitor_host=monitor_host,
    )


"""
UPDATES
"""


@app.route("/isard-admin/admin/updates", methods=["GET"])
@login_required
@isAdmin
def admin_updates():
    return render_template(
        "admin/pages/updates.html",
        title="Downloads",
        nav="Downloads",
        monitor_host=monitor_host,
    )


"""
CONFIG
"""


@app.route("/isard-admin/admin/schedulers", methods=["GET"])
@login_required
@isAdmin
def admin_schedulers():
    return render_template(
        "admin/pages/schedulers.html",
        nav="Schedulers",
        title="Schedulers",
        monitor_host=monitor_host,
    )


@app.route("/isard-admin/admin/notification_tmpls", methods=["GET"])
@login_required
@isAdmin
def admin_notification_tmpls():
    return render_template(
        "admin/pages/notification_tmpls.html",
        nav="Notification templates",
        title="Notification Templates",
        monitor_host=monitor_host,
    )


@app.route("/isard-admin/admin/system", methods=["GET"])
@login_required
@isAdmin
def admin_system():
    return render_template(
        "admin/pages/system.html",
        nav="System",
        title="System",
        monitor_host=monitor_host,
    )


"""
ANALYTICS
"""


@app.route("/isard-admin/admin/analytics", methods=["GET"])
@login_required
@isAdminManager
def admin_analytics():
    return render_template(
        "admin/pages/analytics.html", nav="Analytics", title="Analytics"
    )


"""
LOGS
"""


@app.route("/isard-admin/admin/logs_desktops", methods=["GET"])
@login_required
@isAdmin
def admin_logs_desktops():
    return render_template(
        "admin/pages/logs_desktops.html",
        title="Logs desktops",
        nav="Logs desktops",
        monitor_host=monitor_host,
    )
