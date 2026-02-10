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

import threading
from abc import ABC

from engine.services.db import new_rethink_connection
from isardvdi_common.rethink_base import RethinkBase


class _ThreadLocalConnection:
    """Descriptor providing a per-thread RethinkDB connection with auto-reconnect."""

    def __init__(self):
        self._local = threading.local()

    def _get_connection(self):
        if not hasattr(self._local, "conn") or not self._local.conn.is_open():
            self._local.conn = new_rethink_connection()
        return self._local.conn

    def __get__(self, obj, objtype=None):
        return self._get_connection()


class RethinkCustomBase(RethinkBase, ABC):
    """
    Manage Rethink Documents with RethinkDB connection from engine.

    Use constructor with keyword arguments to create new Rethink Documents or
    update an existing one using id keyword. Use constructor with id as first
    argument to create an object representing an existing Rethink Document.
    """

    _rdb_connection = _ThreadLocalConnection()
