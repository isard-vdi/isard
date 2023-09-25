#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2022-2023 Simó Albert i Beltran
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

import json
from abc import ABC
from time import time

from api.libv2.flask_rethink import RDB
from isardvdi_common.rethink_base import RethinkBase

from api import app, socketio


class RethinkCustomBase(RethinkBase, ABC):
    """
    Manage Rethink Documents with RethinkDB connection from Flask and socketio
    updates.

    Use constructor with keyword arguments to create new Rethink Documents or
    update an existing one using id keyword. Use constructor with id as first
    argument to create an object representing an existing Rethink Document.
    """

    _rdb_context = app.app_context

    _rdb_flask = RDB(app)

    @classmethod
    @property
    def _rdb_connection(cls):
        return cls._rdb_flask.conn

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        socketio.emit(
            self._rdb_table,
            json.dumps(kwargs),
            namespace="/administrators",
            room="admins",
        )

    def __setattr__(self, name, value):
        super().__setattr__(name, value)
        updated_data = {name: value}
        if name == "status":
            updated_data["status_time"] = time()
        updated_data["id"] = self.id
        socketio.emit(
            self._rdb_table,
            json.dumps(updated_data),
            namespace="/administrators",
            room="admins",
        )
