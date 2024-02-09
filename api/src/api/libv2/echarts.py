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

from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone

from rethinkdb import RethinkDB

from api import app

from .flask_rethink import RDB

r = RethinkDB()
db = RDB(app)
db.init_app(app)

from .datatables import TABLE_INDEXS


def get_daily_items(table, date_field):
    with app.app_context():
        data = (
            r.table(table)
            .group(
                lambda match: [
                    match[date_field].year(),
                    match[date_field].month(),
                    match[date_field].day(),
                ]
            )
            .count()
            .run(db.conn)
        )
    return {
        "x": [datetime(*k).isoformat() for k in data.keys()],
        "series": {date_field: [v for v in data.values()]},
    }


def get_grouped_data(table, field):
    query = r.table(table)
    query = (
        query.group(index=field) if field in TABLE_INDEXS[table] else query.group(field)
    )
    with app.app_context():
        data = query.count().run(db.conn)
    return [{"value": v, "name": k} for k, v in data.items() if k is not None]


def get_grouped_unique_data(table, field, unique_field):
    query = r.table(table)
    query = (
        query.group(index=field) if field in TABLE_INDEXS[table] else query.group(field)
    )
    query = query.map(lambda group: group[unique_field]).distinct().count()
    with app.app_context():
        data = query.run(db.conn)
    return [{"value": v, "name": k} for k, v in data.items() if k is not None]


def get_nested_array_grouped_data(table, array_field, field):
    data = (
        r.table(table)
        .concat_map(
            lambda doc: doc[array_field].map(
                lambda array: {
                    "desktop_id": doc["desktop_id"],
                    field: array[field],
                }
            )
        )
        .group(field)
        .count()
        .run(db.conn)
    )
    return [{"value": v, "name": k} for k, v in data.items() if k is not None]
