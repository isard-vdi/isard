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

"""Storage usage data access for the daily consolidator."""

from isardvdi_common.connections.rethink_shared_connection import (
    RethinkSharedConnection,
)
from rethinkdb import r


class StorageUsageProcessed(RethinkSharedConnection):
    """Layer-2 helpers for the storage consolidator."""

    @classmethod
    def fetch_storages(cls) -> list[dict]:
        """Return ready / orphan ``storage`` rows with sized info.

        Pulls only the fields the consolidator needs: id, user_id and
        the qemu-img ``actual-size`` (used to compute the ``size``
        consumption parameter).
        """
        with cls._rdb_context():
            return list(
                r.table("storage")
                .get_all(r.args(["ready", "orphan"]), index="status")
                .pluck(
                    [
                        "id",
                        "user_id",
                        {"qemu-img-info": {"actual-size": True}},
                    ]
                )
                .merge({"item_id": r.row["id"]})
                .run(cls._rdb_connection)
            )
