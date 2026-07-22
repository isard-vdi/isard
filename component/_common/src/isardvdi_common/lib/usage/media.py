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

"""Media usage data access for the daily consolidator."""

from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from rethinkdb import r


class MediaUsageProcessed(RethinkSharedConnection):
    """Layer-2 helpers for the media consolidator."""

    @classmethod
    def fetch_media(cls) -> list[dict]:
        """Return all ``Downloaded`` media rows with sized info.

        Only the consolidator's required fields are plucked: id, user
        and the progress ``total_bytes`` (used to compute ``mda_size``).
        """
        with cls._rdb_context():
            return list(
                r.table("media")
                .get_all("Downloaded", index="status")
                .pluck(["id", "user", {"progress": {"total_bytes": True}}])
                .run(cls._rdb_connection)
            )
