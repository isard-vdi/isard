#
#   Copyright © 2025 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

from flask import jsonify, make_response, redirect, render_template
from flask_login import current_user, login_required, login_user, logout_user

from webapp import app

from .._common.tokens import get_expired_user_data
from ..auth.authentication import *
from ..lib.log import *
from .decorators import isAdmin, isAdminManager, maintenance

monitor_host = os.getenv("GRAFANA_WEBAPP_URL")
if not monitor_host:
    monitor_host = f'https://{os.getenv("DOMAIN", "localhost")}/monitor'


show_operations = os.getenv("OPERATIONS_API_ENABLED")
if show_operations is None:
    show_operations = False
else:
    show_operations = show_operations.lower() == "true"


def render_webapp(*args, **kwargs):
    """
    Centralized render_template function with common parameters
    """
    return render_template(
        *args,
        **kwargs,
        monitor_host=monitor_host,
        show_operations=show_operations,
    )


@app.route("/isard-admin/admin/landing", methods=["GET"])
@login_required
@maintenance
def admin_landing():
    if current_user.is_admin:
        return render_webapp(
            "admin/pages/hypervisors.html",
            title="Hypervisors",
            header="Hypervisors",
            nav="Hypervisors",
        )
    if current_user.role == "manager":
        return render_webapp(
            "admin/pages/analytics.html", nav="Analytics", title="Analytics"
        )


@app.route("/isard-admin/about", methods=["GET"])
@maintenance
def about():
    return render_webapp(
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
        logout_user()
        login_user(user)
        return jsonify(success=True)
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
    if request.cookies.get("isardvdi_session"):
        user_session = get_expired_user_data(request.cookies.get("isardvdi_session"))
        provider = (
            "form"
            if user_session.get("provider") in ["local", "ldap"]
            else user_session.get("provider")
        )
        if response.status_code == 200:
            login_path = f"/login/{provider}/{response.text}"
        else:
            login_path = f"/login/{provider}"
    else:
        login_path = "/login"

    response = make_response(
        f"""
            <!DOCTYPE html>
            <html>
                <body>
                    <script>
                        document.cookie = 'isardvdi_session=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;'
                        document.cookie = 'authorization=; expires=Thu, 01 Jan 1970 00:00:00 UTC; path=/;'
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
    return render_webapp(
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
@maintenance
def admin_domains(nav="Domains"):
    icon = ""
    if nav == "Desktops":
        icon = "desktop"
        return render_webapp(
            "admin/pages/desktops.html",
            title=nav,
            nav=nav,
            icon=icon,
        )
    if nav == "Templates":
        icon = "cubes"
        return render_webapp(
            "admin/pages/templates.html",
            title=nav,
            nav=nav,
            icon=icon,
        )
    if nav == "Deployments":
        icon = "tv"
        return render_webapp(
            "admin/pages/deployments.html",
            title=nav,
            nav=nav,
            icon=icon,
        )
    if nav == "Storage":
        icon = "folder-open"
        return render_webapp(
            "admin/pages/storage.html",
            title=nav,
            nav=nav,
            icon=icon,
        )
    if nav == "Bases":
        icon = "cubes"
    if nav == "Resources":
        icon = "arrows-alt"
        return render_webapp(
            "admin/pages/domains_resources.html",
            title=nav,
            nav=nav,
            icon=icon,
        )
    if nav == "Bookables":
        icon = "briefcase"
        return render_webapp(
            "admin/pages/bookables.html",
            title=nav,
            nav=nav,
            icon=icon,
        )
    if nav == "BookablesEvents":
        icon = "history"
        return render_webapp(
            "admin/pages/bookables_events.html",
            title=nav,
            nav=nav,
            icon=icon,
        )
    if nav == "Priority":
        icon = "briefcase"
        return render_webapp(
            "admin/pages/bookables_priority.html",
            title=nav,
            nav=nav,
            icon=icon,
        )
    if nav == "Recyclebin":
        icon = "trash"
        return render_webapp(
            "admin/pages/recyclebin.html", title=nav, nav=nav, icon=icon
        )

    return render_webapp(
        "admin/pages/desktops.html",
        title=nav,
        nav=nav,
        icon=icon,
    )


@app.route("/isard-admin/admin/domains/render/Recyclebin/<nav>")
@login_required
@isAdminManager
@maintenance
def admin_recyclebin(nav="Disks"):
    if nav == "Domains":
        icon = "dektop"
        return render_webapp(
            "admin/pages/recyclebin_domains.html", title=nav, nav=nav, icon=icon
        )
    if nav == "Config":
        icon = "gears"
        return render_webapp(
            "admin/pages/recyclebin_config.html", title=nav, nav=nav, icon=icon
        )


@app.route("/isard-admin/admin/domains/render/status")
@login_required
@isAdmin
def admin_desktops_status(nav="Desktops Status"):
    icon = "dektop"
    return render_webapp(
        "admin/pages/desktops_status.html", title=nav, nav=nav, icon=icon
    )


"""
MEDIA
"""


@app.route("/isard-admin/admin/isard-admin/media", methods=["POST", "GET"])
@login_required
@isAdminManager
@maintenance
def admin_media():
    return render_webapp(
        "admin/pages/media.html",
        nav="Media",
        title="Media",
    )


"""
USERS
"""


@app.route("/isard-admin/admin/users/<nav>", methods=["POST", "GET"])
@login_required
@isAdminManager
@maintenance
def admin_users(nav):
    if nav == "Management":
        return render_webapp(
            "admin/pages/users_management.html",
            nav=nav,
            title="Management",
        )
    elif nav == "QuotasLimits":
        return render_webapp(
            "admin/pages/users_quotas_limits.html",
            nav=nav,
            title="Quotas / Limits",
        )


@app.route("/isard-admin/admin/users/UserStorage", methods=["POST", "GET"])
@login_required
@isAdmin
def admin_users_user_storage():
    return render_webapp(
        "admin/pages/user_storage.html",
        nav="UserStorage",
        title="User Storage",
    )


@app.route("/isard-admin/admin/users/pwd_policies", methods=["POST", "GET"])
@login_required
@isAdmin
def admin_users_pwd_policies():
    return render_webapp(
        "admin/pages/users_pwd_policies.html",
        nav="Pwd Policies",
        title="Policies",
    )


@app.route("/isard-admin/admin/users/migration", methods=["POST", "GET"])
@login_required
@isAdmin
def admin_users_pwd_migration():
    return render_webapp(
        "admin/pages/migration.html",
        nav="Migration",
        title="Migration",
    )


"""
USAGE
"""


@app.route("/isard-admin/admin/usage", methods=["GET"])
@login_required
@isAdminManager
@maintenance
def admin_usage():
    return render_webapp(
        "admin/pages/usage.html",
        nav="Usage",
        title="Usage",
    )


@app.route("/isard-admin/admin/usage_config", methods=["GET"])
@login_required
@isAdminManager
@maintenance
def admin_usage_config():
    return render_webapp(
        "admin/pages/usage_config.html",
        nav="Usage config",
        title="Usage config",
    )


"""
INFRASTRUCTURE
"""


@app.route("/isard-admin/admin/hypervisors", methods=["GET"])
@login_required
@isAdmin
def admin_hypervisors():
    return render_webapp(
        "admin/pages/hypervisors.html",
        title="Hypervisors",
        header="Hypervisors",
        nav="Hypervisors",
    )


if show_operations:

    @app.route("/isard-admin/admin/operations", methods=["GET"])
    @login_required
    @isAdmin
    def admin_operations():
        return render_webapp(
            "admin/pages/operations.html",
            title="Operations",
            nav="Operations",
        )


@app.route("/isard-admin/admin/queues", methods=["GET"])
@login_required
@isAdmin
def queues():
    """
    Storage Nodes
    """
    return render_webapp(
        "admin/pages/queues.html",
        title="Queues registeres",
        nav="Queues",
    )


@app.route("/isard-admin/admin/storage_pools", methods=["GET"])
@login_required
@isAdmin
def storage_pools():
    """
    Storage Pools
    """
    return render_webapp(
        "admin/pages/storage_pools.html",
        title="Storage Pools",
        nav="Storage Pools",
    )


"""
UPDATES
"""


@app.route("/isard-admin/admin/updates", methods=["GET"])
@login_required
@isAdmin
def admin_updates():
    return render_webapp(
        "admin/pages/updates.html",
        title="Downloads",
        nav="Downloads",
    )


"""
CONFIG
"""


@app.route("/isard-admin/admin/schedulers", methods=["GET"])
@login_required
@isAdmin
def admin_schedulers():
    return render_webapp(
        "admin/pages/schedulers.html",
        nav="Schedulers",
        title="Schedulers",
    )


@app.route("/isard-admin/admin/notifications", methods=["GET"])
@login_required
@isAdmin
def admin_notifications():
    return render_webapp(
        "admin/pages/notifications.html",
        nav="Notification",
        title="Notification",
    )


@app.route("/isard-admin/admin/viewers", methods=["GET"])
@login_required
@isAdmin
def admin_viewers():
    return render_webapp(
        "admin/pages/viewers_config.html",
        nav="Viewers config",
        title="Viewers configuration",
    )


@app.route("/isard-admin/admin/users/authentication", methods=["POST", "GET"])
@login_required
@isAdmin
def admin_users_authentication():
    return render_webapp(
        "admin/pages/authentication.html",
        nav="authentication",
        title="Authentication",
    )


@app.route("/isard-admin/admin/system", methods=["GET"])
@login_required
@isAdmin
def admin_system():
    return render_webapp(
        "admin/pages/system.html",
        nav="System",
        title="System",
    )


"""
ANALYTICS
"""


@app.route("/isard-admin/admin/analytics", methods=["GET"])
@login_required
@isAdminManager
@maintenance
def admin_analytics():
    return render_webapp(
        "admin/pages/analytics.html", nav="Analytics", title="Analytics"
    )


@app.route("/isard-admin/admin/analytics_config", methods=["GET"])
@login_required
@isAdmin
def admin_analytics_config():
    return render_webapp(
        "admin/pages/analytics_config.html",
        nav="Analytics config",
        title="Analytics config",
    )


"""
LOGS
"""


@app.route("/isard-admin/admin/logs_desktops", methods=["GET"])
@login_required
@isAdmin
def admin_logs_desktops():
    return render_webapp(
        "admin/pages/logs_desktops.html",
        title="Logs desktops",
        nav="Logs desktops",
    )


@app.route("/isard-admin/admin/logs_desktops_config", methods=["GET"])
@login_required
@isAdmin
def admin_logs_desktops_config():
    return render_webapp(
        "admin/pages/logs_desktops_config.html",
        title="Logs desktops config",
        nav="Logs desktops config",
    )


@app.route("/isard-admin/admin/logs_users", methods=["GET"])
@login_required
@isAdmin
def admin_logs_users():
    return render_webapp(
        "admin/pages/logs_users.html",
        title="Logs users",
        nav="Logs users",
    )


@app.route("/isard-admin/admin/logs_users_config", methods=["GET"])
@login_required
@isAdmin
def admin_logs_users_config():
    return render_webapp(
        "admin/pages/logs_users_config.html",
        title="Logs users config",
        nav="Logs users config",
    )
