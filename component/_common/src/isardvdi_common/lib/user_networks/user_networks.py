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

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from rethinkdb import r


class UserNetworksProcessed(RethinkSharedConnection):

    _rdb_table = "user_networks"

    @classmethod
    def list_all(cls) -> list[dict]:
        """Return every row in ``user_networks``.

        Role-based filtering is performed in the apiv4 service layer (it
        is authorisation logic, not a generic data-access concern).
        """
        with cls._rdb_context():
            return list(r.table(cls._rdb_table).run(cls._rdb_connection))

    @classmethod
    def get(cls, network_id: str) -> dict | None:
        """Return one row by id, or ``None`` when not found."""
        with cls._rdb_context():
            return r.table(cls._rdb_table).get(network_id).run(cls._rdb_connection)

    @classmethod
    def exists_by_metadata_id(cls, metadata_id: int) -> bool:
        """Return ``True`` if a row with this ``metadata_id`` already exists.

        The metadata_id is a 64-bit derivative of the network UUID; the
        service generates UUIDs in a loop until it finds one whose
        metadata_id is unused. This helper backs that loop.
        """
        with cls._rdb_context():
            hits = list(
                r.table(cls._rdb_table)
                .get_all(metadata_id, index="metadata_id")
                .limit(1)
                .run(cls._rdb_connection)
            )
        return bool(hits)

    @classmethod
    def insert(cls, network: dict) -> None:
        """Insert a fully-shaped network row.

        The caller (apiv4 service) is responsible for shaping the row —
        id, metadata_id, allowed dict, ownership, timestamps. This
        method is intentionally a thin write wrapper.
        """
        with cls._rdb_context():
            r.table(cls._rdb_table).insert(network).run(cls._rdb_connection)

    @classmethod
    def update(cls, network_id: str, update_data: dict) -> None:
        """Apply ``update_data`` to the row with ``network_id``.

        Idempotent on a missing row (rdb returns skipped=1, no error).
        """
        with cls._rdb_context():
            r.table(cls._rdb_table).get(network_id).update(update_data).run(
                cls._rdb_connection
            )

    @classmethod
    def delete(cls, network_id: str) -> None:
        """Delete the row with ``network_id``.

        Idempotent on a missing row (rdb returns deleted=0, no error).
        """
        with cls._rdb_context():
            r.table(cls._rdb_table).get(network_id).delete().run(cls._rdb_connection)
