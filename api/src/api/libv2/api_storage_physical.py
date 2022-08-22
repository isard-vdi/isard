#
#   Copyright © 2022 Josep Maria Viñolas Auquer
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

from .api_exceptions import Error

r = RethinkDB()
import csv
import io
import traceback

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

from .api_exceptions import Error
from .helpers import get_user_data
from .validators import _validate_item, _validate_table


def phy_storage_list(table, kind=None):
    query = r.table("storage_physical_" + table)
    if kind:
        query = query.get_all(kind, index="kind")
    if table == "domains":
        query = query.merge(
            lambda store: {
                "domains": r.table("domains")
                .get_all(store["path"], index="disk_paths")
                .count()
            }
        )
    with app.app_context():
        return list(query.run(db.conn))


def phy_storage_reset(table, data):
    with app.app_context():
        indb = r.table("storage_physical_" + table)["id"].run(db.conn)
        new = [d["id"] for d in data]
        deleted_items = list(set(indb) - set(new))
        for item in deleted_items:
            r.table("storage_physical_" + table).get(item).delete().run(db.conn)
        return phy_storage_update(table, data)


def phy_storage_update(table, data):
    with app.app_context():
        return r.table("storage_physical_" + table).insert(data).run(db.conn)


def phy_storage_delete(table, path_id):
    with app.app_context():
        return r.table("storage_physical_" + table).get(path_id).delete().run(db.conn)
