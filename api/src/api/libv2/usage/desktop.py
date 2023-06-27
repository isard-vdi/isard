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
from .common import get_abs_consumptions, get_params_item_type_custom, securize_eval
from .consolidate import ConsolidateConsumption

r = RethinkDB()
db = RDB(app)
db.init_app(app)


## Data comes from logs_desktops table
## Dates in logs_desktops are in UTC, so we need to filter also in utc
## This launched during 2023-06-20 will get data from 2023-06-19 00:00:00 to 2023-06-20 00:00:00 (not included)
# date = r.iso8601("2023-06-19T23:00:00+00:00").run(dbconn)
# r.table("tests").insert([{"date": date}]).run(dbconn)
# today = get_relative_date(0)
# yesterday = get_relative_date(-1)
# data_today = len(
#     list(r.table("tests").between(yesterday, today, index="date").run(dbconn))
# )

CONSUMERS = {
    "user": "owner_user_id",
    "group": "owner_group_id",
    "category": "owner_category_id",
    "desktop": "desktop_id",
    "deployment": "deployment_id",
    "template": "template_id",
    "hypervisor": "hyp_started",
}


def get_relative_date(days):
    # We use the same function as in consolidate.py as dates in logs_desktops table are also in UTC
    return datetime.now().astimezone().replace(
        minute=0, hour=0, second=0, microsecond=0, tzinfo=pytz.utc
    ) + timedelta(days=days)


class ConsolidateDesktopConsumption(ConsolidateConsumption):
    def __init__(self, days_before=1):
        super().__init__("desktop", DesktopsUsage, days_before)


class DesktopsUsage:
    def __init__(self, days_before=1):
        # logs_desktops dates are in UTC so we use the same as in base class (UTC)
        self.consolidation_day_after = get_relative_date(-(days_before - 1))
        self.consolidation_day = get_relative_date(-days_before)
        self.consolidation_day_before = get_relative_date(-days_before - 1)

        self.consumers = CONSUMERS
        self.consumer_items = list(CONSUMERS.keys())

        self.day_data = self._get_data()
        # We should add any previous data in any previous day for the items found in self.day_data
        if self.day_data:
            self.has_data = True
            self.previous_abs_data = get_abs_consumptions(
                "desktop", self.consolidation_day_before
            )
            self.calculations_are_incremental = True
            self.custom_params = get_params_item_type_custom("desktop", True)
        else:
            self.has_data = False

    def _get_data(self):
        t = time()
        data = list(
            r.table("logs_desktops")
            .without("events")
            .filter(
                lambda log: (
                    log["stopped_time"]
                    > self.consolidation_day | log.has_fields("stopped_time").not_()
                )
                & (log["started_time"] < self.consolidation_day_after)
            )
            .merge(
                r.branch(
                    r.row["started_time"] < self.consolidation_day,
                    {"started_time": self.consolidation_day},
                    {},
                )
            )
            .merge(
                r.branch(
                    r.row["stopped_time"] > self.consolidation_day_after,
                    {"stopped_time": self.consolidation_day_after},
                    {},
                )
            )
            .merge(
                {
                    "template_id": r.row["desktop_template_hierarchy"].default([None])[
                        -1
                    ],
                    "deployment_id": r.row["tag"].default(None),
                }
            )
            .run(db.conn)
        )
        return data

    def _process_consumption(self, consumption):
        if "hardware_bookables_gpu" in consumption:
            gpu_mem = int(
                consumption["hardware_bookables_vgpus"].split("_")[2][:-1]
            )  # Memory GB from profile
        else:
            gpu_mem = 0
        return self._calculate_consumption(
            consumption["started_time"],
            consumption["stopped_time"],
            consumption["hardware_vcpus"],
            gpu_mem,
            consumption["hardware_memory"],
        )

    def _calculate_consumption(
        self, start, stop, vcpus, gpu_mem, memory, interval="hour"
    ):
        # This calculates increment in one start/stop
        interval = 1 / 60 if interval == "hour" else 1
        interval = 1 / 60 / 24 if interval == "day" else interval

        minutes = (stop - start).total_seconds() / 60
        memory = round(memory / 1048576, 0)  # Memory in GB
        params = {
            "dsk_starts": 1,
            "dsk_hours": round(minutes / 60, 2),
            "dsk_gpu_mem": round(gpu_mem * interval * minutes, 2),
            "dsk_gpu_hours": round(minutes / 60 if gpu_mem else 0, 2),
            "dsk_vcpus": round(vcpus * interval * minutes, 2),
            "dsk_mem": round(memory * interval * minutes, 2),
        }

        for param in self.custom_params:
            params[param["id"]] = round(securize_eval(param["formula"], params), 2)
        return params
