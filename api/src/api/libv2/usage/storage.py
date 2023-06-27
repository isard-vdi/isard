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
#   You shouitem_day_data have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later


from datetime import datetime, timedelta
from time import time

import pytz
from rethinkdb import RethinkDB

from api import app

from ..flask_rethink import RDB
from .common import (
    get_abs_consumptions,
    get_owner_info,
    get_params_item_type_custom,
    securize_eval,
)
from .consolidate import ConsolidateConsumption

r = RethinkDB()
db = RDB(app)
db.init_app(app)

CONSUMERS = {
    "user": "owner_user_id",
    "group": "owner_group_id",
    "category": "owner_category_id",
}


def get_relative_date(days):
    # We use the same function as in consolidate.py as dates in logs_desktops table are also in UTC
    return datetime.now().astimezone().replace(
        minute=0, hour=0, second=0, microsecond=0, tzinfo=pytz.utc
    ) + timedelta(days=days)


class ConsolidateStorageConsumption(ConsolidateConsumption):
    def __init__(self, days_before=1):
        super().__init__("storage", StorageUsage, days_before)


# Gets the data for the day from current tables
class StorageUsage:
    def __init__(self, days_before=1):
        # logs_desktops dates are in UTC so we use the same as in base class (UTC)
        self.consolidation_day = get_relative_date(-days_before)
        self.consolidation_day_before = get_relative_date(-days_before - 1)

        self.consumers = CONSUMERS
        self.consumer_items = list(CONSUMERS.keys())

        self.day_data = self._get_data()
        if self.day_data:
            self.has_data = True
            self.previous_abs_data = get_abs_consumptions(
                "storage", self.consolidation_day_before
            )
            self.calculations_are_incremental = False
            self.custom_params = get_params_item_type_custom("storage", True)
        else:
            self.has_data = False

    def _get_data(self):
        t = time()
        with app.app_context():
            storage = list(
                r.table("storage")
                .get_all(r.args(["ready", "orphan"]), index="status")
                .pluck(["id", "user_id", {"qemu-img-info": {"actual-size": True}}])
                .merge({"item_id": r.row["id"]})
                .run(db.conn)
            )
        data = [
            {
                **s,
                **get_owner_info(s["user_id"]),
                **{
                    "size": s.get("qemu-img-info", {}).get("actual-size", 0),
                    "started_time": self.consolidation_day,
                    "stopped_time": self.consolidation_day,
                },
            }
            for s in storage
        ]
        return data

    def _process_consumption(self, consumption):
        return self._calculate_consumption(
            consumption["size"],
        )

    def _calculate_consumption(self, size):
        size = round(size / 1073741824, 2)
        params = {
            "str_created": 1,
            "str_size": size,
        }

        for param in self.custom_params:
            params[param["id"]] = round(securize_eval(param["formula"], params), 2)
        return params
