#
#   Copyright © 2023 Josep Maria Viñolas Auquer
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

from flask_login import LoginManager, UserMixin
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()

from ..libv2.flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from cachetools import TTLCache, cached

from ..libv2.log import *

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"


class User(UserMixin):
    def __init__(self, dict):
        self.id = dict["id"]
        self.provider = dict["provider"]
        self.category = dict["category"]
        self.uid = dict["uid"]
        self.username = dict["username"]
        self.name = dict["name"]
        self.role = dict["role"]
        self.group = dict["group"]
        self.path = (
            dict["category"]
            + "/"
            + dict["group_uid"]
            + "/"
            + dict["provider"]
            + "/"
            + dict["uid"]
            + "-"
            + dict["username"]
            + "/"
        )
        self.email = dict["email"]
        self.quota = dict["quota"]
        self.auto = dict["auto"] if "auto" in dict.keys() else False
        self.is_admin = True if self.role == "admin" else False
        self.active = dict["active"]
        self.tags = dict.get("tags", [])
        self.photo = dict["photo"]


@cached(TTLCache(maxsize=10, ttl=5))
@login_manager.user_loader
def user_loader(username):
    with app.app_context():
        user = r.table("users").get(username).run(db.conn)
    if not user:
        return
    return User(user)
