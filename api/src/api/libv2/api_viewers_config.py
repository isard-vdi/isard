#
#   Copyright © 2024 Miriam Melina Gamboa Valdez
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

from cachetools import TTLCache, cached
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()

from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

_viewers = TTLCache(maxsize=1, ttl=3600)

## Config view functions


def get_viewers_config():
    custom = []
    with app.app_context():
        viewers = (
            r.table("config").get(1).pluck("viewers")["viewers"].keys().run(db.conn)
        )
        for viewer in viewers:
            custom.append(
                r.table("config")
                .get(1)
                .pluck("viewers")["viewers"][viewer]
                .run(db.conn)
            )
    return custom


def update_viewers_config(viewer, custom):
    with app.app_context():
        r.table("config").get(1).update({"viewers": {viewer: {"custom": custom}}}).run(
            db.conn
        )


def reset_viewers_config(viewer):
    with app.app_context():
        r.table("config").get(1).update(
            {"viewers": {viewer: {"custom": r.row["viewers"][viewer]["default"]}}}
        ).run(db.conn)


## IsardVDI viewers configuration


@cached(_viewers)
def get_viewers():
    with app.app_context():
        return r.table("config").get(1).pluck("viewers")["viewers"].run(db.conn)


def rdp_file_viewer():
    return get_viewers()["file_rdpvpn"]


def rdpgw_file_viewer():
    return get_viewers()["file_rdpgw"]


def spice_file_viewer():
    return get_viewers()["file_spice"]
