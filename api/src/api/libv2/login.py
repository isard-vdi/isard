#
#   Copyright © 2024 Pau Abril Iranzo
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

from rethinkdb import RethinkDB

from api import app

from .caches import config_cache
from .flask_rethink import RDB

r = RethinkDB()
db = RDB(app)
db.init_app(app)


def update_login_notification(data):
    config_cache.clear()
    with app.app_context():
        return (
            r.table("config")
            .get(1)
            .update(
                {
                    "login": {
                        "notification_cover": data.get("cover", None),
                        "notification_form": data.get("form", None),
                    }
                }
            )
            .run(db.conn)
        )


def enable_login_notification(type, enable: bool):
    config_cache.clear()
    with app.app_context():
        return (
            r.table("config")
            .get(1)
            .update({"login": {f"notification_{type}": {"enabled": enable}}})
            .run(db.conn)
        )
