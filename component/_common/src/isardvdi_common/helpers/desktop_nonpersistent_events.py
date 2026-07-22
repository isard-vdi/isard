#
#   Copyright © 2025 Miriam Melina Gamboa Valdez
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
from isardvdi_common.schemas.domains import DesktopStatusEnum
from rethinkdb import r


class DesktopNonpersistentEvents(RethinkSharedConnection):

    _rdb_table = "domains"

    @classmethod
    def desktops_non_persistent_delete(cls, user_id, template):
        """_From api/libv2/api_nonpersistentdesktop_events.py desktops_non_persistent_delete()_"""
        with cls._rdb_context():
            r.table(cls._rdb_table).get_all(user_id, index="user").filter(
                {"from_template": template, "persistent": False}
            ).update({"status": DesktopStatusEnum.force_deleting.value}).run(
                cls._rdb_connection
            )

    @classmethod
    def desktop_non_persistent_delete(cls, desktop_id):
        """_From api/libv2/api_nonpersistentdesktop_events.py desktop_non_persistent_delete()_"""
        with cls._rdb_context():
            r.table(cls._rdb_table).get(desktop_id).update(
                {"status": DesktopStatusEnum.force_deleting.value}
            ).run(cls._rdb_connection)
