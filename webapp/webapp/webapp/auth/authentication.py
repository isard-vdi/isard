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

from flask import render_template, request
from flask_login import LoginManager, UserMixin
from isardvdi_apiv4_client.api.role_manager import admin_get_user_raw
from isardvdi_apiv4_client.api.role_user import get_user_details
from isardvdi_apiv4_client_auth import ApiV4Error, build_client, raise_for_status
from rethinkdb import RethinkDB

from webapp import app

from ..views.decorators import maintenance

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


@maintenance
@login_manager.user_loader
def user_loader(user_id):
    try:
        with build_client("isard-webapp") as client:
            resp = admin_get_user_raw.sync_detailed(client=client, user_id=user_id)
            raise_for_status(resp)
        user = json.loads(resp.content.decode("utf-8")) if resp.content else None
        if user is None:
            return
        return User(user)
    except ApiV4Error:
        return render_template("maintenance.html"), 503
    except Exception:
        return render_template("maintenance.html"), 503


@maintenance
def user_reloader(user_id):
    try:
        with build_client("isard-webapp") as client:
            resp = admin_get_user_raw.sync_detailed(client=client, user_id=user_id)
            raise_for_status(resp)
        user = json.loads(resp.content.decode("utf-8")) if resp.content else None
        if user is None:
            return
        return User(user)
    except ApiV4Error:
        return render_template("maintenance.html"), 503
    except Exception:
        return render_template("maintenance.html"), 503
