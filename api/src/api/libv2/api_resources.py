#
#   Copyright © 2024 Naomi Hidalgo
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

r = RethinkDB()
from .flask_rethink import RDB

db = RDB(app)
db.init_app(app)

## QOS Disk


def add_qos_disk(data):
    with app.app_context():
        r.table("qos_disk").insert(data).run(db.conn)


def update_qos_disk(qos_disk_id, data):
    with app.app_context():
        r.table("qos_disk").get(qos_disk_id).update(data).run(db.conn)


def check_qos_burst_limits(iotune):
    errors = []
    for key, value in iotune.items():
        if "_sec" in key and not key.endswith("_max"):
            app.logger.error(key)
            max_key = key + "_max"
            if max_key in iotune:
                if iotune[max_key] < value:
                    errors.append(
                        f"{key} burst value should be higher than limit value"
                    )
    if errors:
        return errors
