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

from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from rethinkdb import r


class DesktopUsageProcessed(RethinkSharedConnection):
    """Layer-2 helpers for the desktop consolidator."""

    @classmethod
    def fetch_logs(
        cls,
        consolidation_day: datetime,
        consolidation_day_after: datetime,
    ) -> list[dict]:
        """Fetch ``logs_desktops`` rows in ``[day, day_after)`` window.

        Rows that started before ``consolidation_day`` are clamped to
        the window edge so consolidation accounting only counts the
        time inside the day. Same for ``stopped_time`` against
        ``consolidation_day_after``. Each row is enriched with
        ``template_id`` (last item of ``desktop_template_hierarchy``,
        or None) and ``deployment_id`` (the row's ``tag``, or None).
        """
        with cls._rdb_context():
            return list(
                r.table("logs_desktops")
                .without("events")
                .filter(
                    lambda log: (
                        (log["stopped_time"] > consolidation_day)
                        | log.has_fields("stopped_time").not_()
                    )
                    & (log["started_time"] < consolidation_day_after)
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
