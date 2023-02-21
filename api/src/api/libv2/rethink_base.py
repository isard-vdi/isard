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
from abc import ABC, abstractmethod
from time import time

from cachetools import TTLCache, cached
from rethinkdb import r

from api import app

from .. import socketio
from .flask_rethink import RDB


class RethinkBase(ABC):
    """
    Manage Rethink Documents.

    Use constructor with keyword arguments to create new Rethink Documents or
    update an existing one using id keyword. Use constructor with id as first
    argument to create an object representing an existing Rethink Document.
    """

    _rdb = RDB(app)

    @property
    @abstractmethod
    def _table(self):
        pass

    def __init__(self, *args, **kwargs):
        if args:
            kwargs["id"] = args[0]
        with app.app_context():
            self.__dict__["id"] = (
                r.table(self._table)
                .insert(kwargs, conflict="update")
                .run(self._rdb.conn)
                .get("generated_keys", [kwargs.get("id")])[0]
            )
        if not "id" in kwargs:
            kwargs["id"] = self.id
        socketio.emit(
            self._table,
            json.dumps(kwargs),
            namespace="/administrators",
            room="admins",
        )

    @cached(TTLCache(maxsize=10, ttl=5))
    def __getattr__(self, name):
        if name in self.__dict__:
            return self.__dict__[name]
        with app.app_context():
            return (
                r.table(self._table)
                .get(self.id)
                .pluck(name)
                .run(self._rdb.conn)
                .get(name)
            )

    def __setattr__(self, name, value):
        if name == "id":
            raise AttributeError
        updated_data = {name: value}
        if name == "status":
            updated_data["status_time"] = time()
        with app.app_context():
            r.table(self._table).get(self.id).update(updated_data).run(self._rdb.conn)
        updated_data["id"] = self.id
        socketio.emit(
            self._table,
            json.dumps(updated_data),
            namespace="/administrators",
            room="admins",
        )
