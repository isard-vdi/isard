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

"""Desktop usage log-data access for the daily consolidator."""

from datetime import datetime
from typing import Iterator

from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from rethinkdb import r

# What the desktop consolidator reads from a log row ("tag" feeds the
# deployment_id merge in iter_logs).
LOG_FIELDS = (
    "desktop_id",
    "desktop_name",
    "desktop_template_hierarchy",
    "owner_user_id",
    "owner_user_name",
    "owner_group_id",
    "owner_group_name",
    "owner_category_id",
    "owner_category_name",
    "deployment_name",
    "tag",
    "hyp_started",
    "started_time",
    "stopped_time",
    "hardware_vcpus",
    "hardware_memory",
    "hardware_bookables_vgpus",
)


class DesktopUsageProcessed(RethinkSharedConnection):
    """Layer-2 helpers for the desktop consolidator."""

    @classmethod
    def iter_logs(
        cls,
        consolidation_day: datetime,
        consolidation_day_after: datetime,
    ) -> Iterator[dict]:
        """Stream ``logs_desktops`` rows in ``[day, day_after)`` window.

        Rows that started before ``consolidation_day`` are clamped to
        the window edge so consolidation accounting only counts the
        time inside the day. Same for ``stopped_time`` against
        ``consolidation_day_after``. Each row is enriched with
        ``template_id`` (last item of ``desktop_template_hierarchy``,
        or None) and ``deployment_id`` (the row's ``tag``, or None).
        Only ``LOG_FIELDS`` are fetched. The pool connection is held until
        the stream is exhausted or closed.
        """
        with cls._rdb_context():
            yield from (
                r.table("logs_desktops")
                .between(r.minval, consolidation_day_after, index="started_time")
                .pluck(*LOG_FIELDS)
                .filter(
                    lambda log: (log["stopped_time"] > consolidation_day)
                    | log.has_fields("stopped_time").not_()
                )
                .merge(
                    r.branch(
                        r.row["started_time"] < consolidation_day,
                        {"started_time": consolidation_day},
                        {},
                    )
                )
                .merge(
                    r.branch(
                        r.row["stopped_time"] > consolidation_day_after,
                        {"stopped_time": consolidation_day_after},
                        {},
                    )
                )
                .merge(
                    {
                        "template_id": r.branch(
                            r.row["desktop_template_hierarchy"].default([]).is_empty(),
                            None,
                            r.row["desktop_template_hierarchy"][-1],
                        ),
                        "deployment_id": r.row["tag"].default(None),
                    }
                )
                .run(cls._rdb_connection)
            )
