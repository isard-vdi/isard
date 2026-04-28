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

import logging
from functools import wraps

from cachetools import TTLCache, cached
from flask import redirect, render_template
from flask_login import current_user, logout_user
from isardvdi_apiv4_client.api.open_ import maintenance_status
from isardvdi_apiv4_client.api.role_admin import get_category_maintenance
from isardvdi_apiv4_client.models import MaintenanceStatusResponse
from isardvdi_apiv4_client_auth import build_client, raise_for_status


def checkRole(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if current_user.role == "user":
            return render_template(
                "pages/desktops.html", title="Desktops", nav="Desktops"
            )
        return fn(*args, **kwargs)

    return decorated_view


def isAdmin(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if current_user.is_admin:
            return fn(*args, **kwargs)
        logout_user()
        return redirect("/login")

    return decorated_view


def isAdminManager(fn):
    @wraps(fn)
    def decorated_view(*args, **kwargs):
        if current_user.is_admin or current_user.role == "manager":
            return fn(*args, **kwargs)
        logout_user()
        return redirect("/login")

    return decorated_view


@cached(TTLCache(maxsize=1, ttl=5))
def _get_maintenance(category_id=None):
    logging.debug("Check api maintenance mode")
    with build_client("isard-webapp") as client:
        if category_id:
            resp = get_category_maintenance.sync_detailed(
                client=client, category_id=category_id
            )
        else:
            resp = maintenance_status.sync_detailed(client=client)
        raise_for_status(resp)
        result = resp.parsed
    if isinstance(result, MaintenanceStatusResponse):
        return bool(result.enabled)
    if isinstance(result, dict):
        return bool(result.get("enabled", False))
    return bool(result)


def maintenance(function):
    """Decorator that returns maintenance response if api is in maintenance mode."""

    @wraps(function)
    def wrapper(*args, **kargs):
        if getattr(current_user, "role", None) != "admin":
            if _get_maintenance(getattr(current_user, "category", None)):
                return render_template("maintenance.html"), 503
        return function(*args, **kargs)

    return wrapper
