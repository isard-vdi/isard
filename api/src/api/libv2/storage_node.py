#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2022 Simó Albert i Beltran
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

from time import time

from cachetools import TTLCache, cached
from rethinkdb import r

from api import app

from .flask_rethink import RDB


class StorageNode:
    """
    Manage Storage Node.

    Use constructor with keyboard arguments to create new Storage Node or
    update an existing one using id keyboard. Use constructor with id as
    first argument to create an object representing an existing Storage
    Node.
    """

    _rdb = RDB(app)

    def __init__(self, *args, **kwargs):
        if args:
            kwargs["id"] = args[0]
        with app.app_context():
            self.__dict__["id"] = (
                r.table("storage_node")
                .insert(kwargs, conflict="update")
                .run(self._rdb.conn)
                .get("generated_keys", [kwargs.get("id")])[0]
            )

    @cached(TTLCache(maxsize=10, ttl=5))
    def __getattr__(self, name):
        if name in self.__dict__:
            return self.__dict__[name]
        with app.app_context():
            return (
                r.table("storage_node")
                .get(self.id)
                .pluck(name)
                .run(self._rdb.conn)
                .get(name)
            )

    def __setattr__(self, name, value):
        if name == "id":
            raise AttributeError
        else:
            updated_data = {name: value}
            if name == "status":
                updated_data["status_time"] = time()
            with app.app_context():
                r.table("storage_node").get(self.id).update(updated_data).run(
                    self._rdb.conn
                )
