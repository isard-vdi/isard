#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Usage reset-date set management (table ``usage_reset_dates``).

Reset dates partition the consumption timeline into segments — when a
desktop or user crosses a reset date, the absolute consumption value
resets to whatever it accumulated since that date instead of since the
beginning of time. The admin route that drives this re-writes the
whole set on every PUT (clear + bulk insert), so the lib helper does
the same.
"""

from datetime import datetime

import pytz
from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from rethinkdb import r


class ResetDatesUsageProcessed(RethinkSharedConnection):
    """Layer-2 helpers for ``usage_reset_dates`` rows."""

    @classmethod
    def list_reset_dates(
        cls,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[datetime]:
        """Return reset dates ``<= end_date`` (or all when no window).

        Sorted ascending. Returns an empty list when the table is empty.
        ``start_date`` is accepted for API symmetry but the original
        query only filters on ``end_date``; we preserve the contract.
        """
        with cls._rdb_context():
            if start_date and end_date:
                within = list(
                    r.table("usage_reset_dates")
                    .filter((r.row["date"] <= end_date))
                    .order_by(r.desc("date"))["date"]
                    .run(cls._rdb_connection)
                )
            else:
                within = list(
                    r.table("usage_reset_dates")
                    .order_by(r.desc("date"))["date"]
                    .run(cls._rdb_connection)
                )
        if within:
            within.reverse()
            return within
        return []

    @classmethod
    def replace_reset_dates(cls, date_list: list[datetime]) -> None:
        """Replace the entire set of reset dates.

        Wipes the table, then inserts each date once with a UTC
        timezone (so comparisons against ``r.row["date"]`` stay on the
        same axis). Duplicates in the input are de-duplicated.
        """
        with cls._rdb_context():
            r.table("usage_reset_dates").delete().run(cls._rdb_connection)
        for date in set(date_list):
            date = date.replace(tzinfo=pytz.timezone("UTC"))
            with cls._rdb_context():
                r.table("usage_reset_dates").insert({"date": date}).run(
                    cls._rdb_connection
                )
