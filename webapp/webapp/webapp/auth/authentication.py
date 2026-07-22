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

import json

from flask import abort, g, request
from flask_login import LoginManager, UserMixin
from isardvdi_apiv4_client.api.role_manager import admin_get_user_raw
from isardvdi_apiv4_client.api.role_user import get_user_details
from isardvdi_apiv4_client_auth import ApiV4Error, build_client, raise_for_status
from rethinkdb import RethinkDB

from webapp import app

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


class User(UserMixin):
    def __init__(self, dict):
        self.id = dict["id"]
        self.role = dict["role"]
        self.is_admin = True if self.role == "admin" else False
        self.category = dict["category"]
        self.name = dict["name"]
        self.username = dict["username"]

    def is_active(self):
        return self.active

    def is_anonymous(self):
        return False


def get_authenticated_user():
    """Check if session is authenticated by jwt

    :returns: User object if authenticated
    """

    auth = request.headers.get("Authorization", None)
    if not auth:
        return None

    # Forward the end-user's JWT so apiv4 resolves them (not the service
    # identity). build_client accepts either service creds or a caller
    # token; strip the Bearer prefix since the client adds it back.
    tkn = auth.split(" ", 1)[1] if auth.startswith("Bearer ") else auth
    with build_client("isard-webapp", user_jwt=tkn) as client:
        response = get_user_details.sync_detailed(client=client)
    if response.status_code == 200:
        return User(json.loads(response.content.decode("utf-8")))
    return None


def _load_user_from_api(user_id):
    """Resolve a session user via apiv4.

    A Flask-Login user-loader callback MUST return a ``User`` or ``None``
    and MUST NOT render a template: ``render_template`` runs Flask-Login's
    ``_user_context_processor``, which calls back into the loader and
    recurses until the stack blows. When apiv4 is unreachable we instead
    ``abort(503)`` so the maintenance page is produced by the 503 error
    handler at the top of the request, outside the loader.

    ``g._isard_api_unreachable`` makes the failure sticky for the rest of
    the request: the 503 handler renders ``maintenance.html``, whose
    template context re-enters this loader once more — that nested call
    short-circuits to ``None`` instead of hitting apiv4 again and
    re-aborting.
    """
    if g.get("_isard_api_unreachable"):
        return None
    try:
        with build_client("isard-webapp") as client:
            resp = admin_get_user_raw.sync_detailed(client=client, user_id=user_id)
            raise_for_status(resp)
        user = json.loads(resp.content.decode("utf-8")) if resp.content else None
        if user is None:
            return None
        return User(user)
    except Exception:
        g._isard_api_unreachable = True
        abort(503)


@login_manager.user_loader
def user_loader(user_id):
    return _load_user_from_api(user_id)


def user_reloader(user_id):
    return _load_user_from_api(user_id)
