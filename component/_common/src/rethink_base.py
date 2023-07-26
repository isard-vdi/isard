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

from abc import ABC, abstractmethod
from time import time

from cachetools import TTLCache, cached
from rethinkdb import r


class Context:
    """
    No-op context
    """

    def __enter__(self):
        pass

    def __exit__(self, *args):
        pass


class RethinkBase(ABC):
    """
    Manage Rethink Documents.

    Use constructor with keyword arguments to create new Rethink Documents or
    update an existing one using id keyword. Use constructor with id as first
    argument to create an object representing an existing Rethink Document.
    """

    _rdb_context = Context

    @property
    @abstractmethod
    def _rdb_connection(self):
        pass

    @property
    @abstractmethod
    def _rdb_table(self):
        pass

    def __init__(self, *args, **kwargs):
        if args:
            kwargs["id"] = args[0]
        with self._rdb_context():
            self.__dict__["id"] = (
                r.table(self._rdb_table)
                .insert(kwargs, conflict="update")
                .run(self._rdb_connection)
                .get("generated_keys", [kwargs.get("id")])[0]
            )
        if "id" not in kwargs:
            kwargs["id"] = self.id

    @cached(TTLCache(maxsize=10, ttl=5))
    def __getattr__(self, name):
        if name in self.__dict__:
            return self.__dict__[name]
        with self._rdb_context():
            return (
                r.table(self._rdb_table)
                .get(self.id)
                .pluck(name)
                .run(self._rdb_connection)
                .get(name)
            )

    def __setattr__(self, name, value):
        if name == "id":
            raise AttributeError
        updated_data = {name: value}
        if name == "status":
            updated_data["status_time"] = time()
        with self._rdb_context():
            r.table(self._rdb_table).get(self.id).update(updated_data).run(
                self._rdb_connection
            )
        updated_data["id"] = self.id

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.id == other.id
        return False

    def __hash__(self):
        return hash(self.id)

    @classmethod
    def exists(cls, document_id):
        """
        Check if a document ID exists.

        :param document_id: Document ID
        :type document_id: str
        :return: True if exists, False otherwise.
        :rtype: bool
        """
        with cls._rdb_context():
            return bool(
                r.table(cls._rdb_table).get(document_id).run(cls._rdb_connection)
            )

    @classmethod
    def get_all(cls):
        """
        Get all documents.

        :return: List of objects.
        :rtype: list
        """
        with cls._rdb_context():
            return [
                cls(document["id"])
                for document in r.table(cls._rdb_table)
                .pluck("id")
                .run(cls._rdb_connection)
            ]

    @classmethod
    @cached(TTLCache(maxsize=100, ttl=5))
    def get_index(cls, values, index, filter=None, pluck=None):
        """
        Get documents with specific index.

        :param values: Array of values
        :type values: list
        :param index: Index name
        :type index: str
        :param filter: Filter
        :type filter: dict
        :param pluck: Pluck
        :type pluck: list
        :return: List of objects.
        :rtype: list
        """
        query = r.table(cls._rdb_table).get_all(r.args(values), index=index)
        query = query.filter(filter) if filter else query
        query = query.pluck(pluck) if pluck else query
        with cls._rdb_context():
            return [cls(document) for document in query.run(cls._rdb_connection)]

    @cached(TTLCache(maxsize=100, ttl=5))
    def get_compound_index(cls, values, index, filter=None, pluck=None):
        """
        Get documents with compound index

        :param values: Array of values
        :type values: list
        :param index: Index name
        :type index: str
        :param filter: Filter
        :type filter: dict
        :param pluck: Pluck
        :type pluck: list
        :return: List of objects.
        :rtype: list
        """
        query = r.table(cls._rdb_table).get_all(r.args(values), index=index)
        query = query.filter(filter) if filter else query
        query = query.pluck(pluck) if pluck else query
        with cls._rdb_context():
            return [cls(document) for document in query.run(cls._rdb_connection)]
