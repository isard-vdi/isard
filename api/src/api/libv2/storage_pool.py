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

from rethinkdb import r

from api import app

from .rethink_base import RethinkBase


class StoragePool(RethinkBase):
    """
    Manage Storage Pool.

    Use constructor with keyword arguments to create new Storage Pool or
    update an existing one using id keyword. Use constructor with id as
    first argument to create an object representing an existing Storage Pool.
    """

    _table = "storage_pool"

    @classmethod
    def get_by_path(cls, path):
        """
        Get Storage Pools that have a specific path

        :param path: Path
        :type path: str
        :return: StoragePool objects
        :rtype: list
        """
        with app.app_context():
            return [
                cls(storage_pool["id"])
                for storage_pool in r.table(cls._table)
                .filter(
                    lambda document: document["paths"]
                    .values()
                    .contains(
                        lambda path_type: path_type.contains(
                            lambda path_dict: path_dict["path"].eq(path)
                        )
                    )
                )
                .pluck("id")
                .run(cls._rdb.conn)
            ]
