#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2023 Simó Albert i Beltran
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

from isardvdi_common.atexit_register import atexit_register
from isardvdi_common.rethink_base import RethinkBase
from rethinkdb import r


class RethinkCustomBase(RethinkBase, ABC):
    """
    Manage Rethink Documents with RethinkDB connection from core_worker.

    Use constructor with keyword arguments to create new Rethink Documents or
    update an existing one using id keyword. Use constructor with id as first
    argument to create an object representing an existing Rethink Document.
    """

    _rdb_connection = r.connect(
        host=environ.get("RETHINKDB_HOST", "isard-db"),
        port=environ.get("RETHINKDB_PORT", "28015"),
        auth_key=environ.get("RETHINKDB_AUTH", ""),
        db=environ.get("RETHINKDB_DB", "isard"),
    )

    @classmethod
    @atexit_register
    def _rethink_disconnect(cls):
        cls._rdb_connection.close()
