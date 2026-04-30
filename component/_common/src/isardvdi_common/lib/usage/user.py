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

"""User usage log-data access for the daily consolidator."""

from datetime import datetime

from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from rethinkdb import r


class UserUsageProcessed(RethinkSharedConnection):
    """Layer-2 helpers for the user consolidator."""

    @classmethod
    def fetch_logs(
        cls,
        consolidation_day: datetime,
        consolidation_day_after: datetime,
    ) -> list[dict]:
        """Fetch ``logs_users`` rows overlapping ``[day, day_after)``.

        Rows that started before ``consolidation_day`` are clamped to
        the window edge so consolidation accounting only counts the
        time inside the day; same for ``stopped_time`` against
        ``consolidation_day_after``.
        """
        with cls._rdb_context():
            return list(
                r.table("logs_users")
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
                .run(cls._rdb_connection)
            )
