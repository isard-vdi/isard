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

import requests
from flask import request
from flask_login import LoginManager, UserMixin
from rethinkdb import RethinkDB

from webapp import app

from .._common.api_rest import ApiRest

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

    response = requests.get(
        "http://isard-api:5000/api/v3/user", headers={"Authorization": auth}
    )
    if response.status_code == 200:
        return User(json.loads(response.text))
    return None


@login_manager.user_loader
def user_loader(user_id):
    user = ApiRest().get(f"/admin/user/{user_id}/raw")
    if user is None:
        return
    return User(user)


def user_reloader(user_id):
    user = ApiRest().get(f"/admin/user/{user_id}/raw")
    if user is None:
        return
    return User(user)
