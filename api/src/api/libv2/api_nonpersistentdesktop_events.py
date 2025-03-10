#
#   Copyright © 2025 Miriam Melina Gamboa Valdez
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

from .caches import get_document

r = RethinkDB()

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)


def desktops_non_persistent_delete(user_id, template):
    with app.app_context():
        r.table("domains").get_all(user_id, index="user").filter(
            {"from_template": template, "persistent": False}
        ).update({"status": "ForceDeleting"}).run(db.conn)


def desktop_non_persistent_delete(desktop_id):
    with app.app_context():
        r.table("domains").get(desktop_id).update({"status": "ForceDeleting"}).run(
            db.conn
        )
