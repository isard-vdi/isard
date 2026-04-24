#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2023,2025 Simó Albert i Beltran
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from abc import ABC
from os import environ

from isardvdi_common.helpers.atexit_register import atexit_register
from rethinkdb import r
from rethinkdb.net import Connection


class Context:
    """
    Ephemeral RethinkDB connection
    """

    def __enter__(self):
        if isinstance(RethinkSharedConnection._rdb_connection, Connection):
            if not RethinkSharedConnection._rdb_connection.is_open():
                RethinkSharedConnection._rdb_connection.close()
                RethinkSharedConnection._rdb_connection = r.connect(
                    host=environ.get("RETHINKDB_HOST", "isard-db"),
                    port=environ.get("RETHINKDB_PORT", "28015"),
                    auth_key=environ.get("RETHINKDB_AUTH", ""),
                    db=environ.get("RETHINKDB_DB", "isard"),
                )

        else:
            RethinkSharedConnection._rdb_connection = r.connect(
                host=environ.get("RETHINKDB_HOST", "isard-db"),
                port=environ.get("RETHINKDB_PORT", "28015"),
                auth_key=environ.get("RETHINKDB_AUTH", ""),
                db=environ.get("RETHINKDB_DB", "isard"),
            )

    def __exit__(self, *args):
        RethinkSharedConnection._rdb_connection.close()


class RethinkSharedConnection(ABC):
    """
    Manage RethinkDB shared connection.

    Open _rdb_context and use _rdb_connection to use a shared connection.
    """

    _rdb_connection = None
    _rdb_context = Context

    @classmethod
    @atexit_register
    def _rethink_disconnect(cls):
        cls._rdb_connection.close()
