#
#   Copyright © 2026 IsardVDI
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

from datetime import datetime

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from rethinkdb import r


def _coerce_timestamp(value: int | float | str | datetime) -> "r.RqlQuery":
    """Convert a Unix int/float, ISO string, or datetime to a ReQL time.

    Non-coercible inputs fall back to ``r.now()`` so the row still lands
    in the table — the backupninja service is the only producer and
    occasionally misformats the timestamp.
    """
    if isinstance(value, (int, float)):
        seconds = value / 1000 if value > 1e10 else value
        return r.epoch_time(seconds)
    if isinstance(value, str):
        try:
            return r.iso8601(value)
        except Exception:
            return r.now()
    if hasattr(value, "isoformat"):
        return r.iso8601(value.isoformat())
    return r.now()


class BackupsProcessed(RethinkSharedConnection):
    """Data-access for the ``backups`` table.

    Validation, retention defaults and the notify-on-failure side-effect
    stay in the apiv4 service — this layer is the persistence interface
    plus the rdb-time coercion (since the ``r.now()`` / ``r.iso8601()``
    expressions only mean anything against the ``rethinkdb`` driver).
    """

    _rdb_table = "backups"

    @classmethod
    def list_recent(cls, limit: int) -> list[dict]:
        """List the ``limit`` most-recent backup records, newest first."""
        with cls._rdb_context():
            return list(
                r.table(cls._rdb_table)
                .order_by(r.desc("timestamp"))
                .limit(limit)
                .run(cls._rdb_connection)
            )

    @classmethod
    def get(cls, backup_id: str, pluck: list[str] | None = None) -> dict | None:
        """Fetch one backup by id; optionally restrict to ``pluck`` fields.

        Returns ``None`` if the row is missing — caller decides whether
        that's a 404 or a fall-back.
        """
        with cls._rdb_context():
            query = r.table(cls._rdb_table).get(backup_id)
            if pluck:
                query = query.pluck(*pluck)
            return query.run(cls._rdb_connection)

    @classmethod
    def insert(cls, data: dict) -> dict:
        """Insert a backup row, coercing ``timestamp`` to ReQL time.

        Mutates ``data`` in place: the client-supplied ``timestamp``
        becomes a ReQL datetime, ``received_at`` is stamped to ``r.now()``,
        and ``created_at`` defaults to ``received_at`` when unset.
        Returns the raw rdb result dict (``inserted``, ``generated_keys``,
        etc.) so the caller can inspect it.
        """
        if "timestamp" in data:
            data["timestamp"] = _coerce_timestamp(data["timestamp"])
        data["received_at"] = r.now()
        data.setdefault("created_at", data["received_at"])

        with cls._rdb_context():
            return r.table(cls._rdb_table).insert(data).run(cls._rdb_connection)

    @classmethod
    def count(cls) -> int:
        """Return the total number of rows in the table."""
        with cls._rdb_context():
            return r.table(cls._rdb_table).count().run(cls._rdb_connection)

    @classmethod
    def list_old_ids(cls, keep: int) -> list[str]:
        """Return the ids of rows older than the ``keep`` newest.

        Backs the retention sweep — newest ``keep`` rows are preserved,
        the rest are returned for deletion.
        """
        with cls._rdb_context():
            return [
                row["id"]
                for row in r.table(cls._rdb_table)
                .order_by(r.desc("timestamp"))
                .skip(keep)
                .pluck("id")
                .run(cls._rdb_connection)
            ]

    @classmethod
    def delete_many(cls, ids: list[str]) -> int:
        """Delete rows by id and return the count of rows removed."""
        if not ids:
            return 0
        with cls._rdb_context():
            result = (
                r.table(cls._rdb_table).get_all(*ids).delete().run(cls._rdb_connection)
            )
        return result.get("deleted", 0)
