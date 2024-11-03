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
from cachetools.keys import hashkey
from rethinkdb import r

_cache = TTLCache(maxsize=10, ttl=5)


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
        self._update_cache(**kwargs)
        if "id" not in kwargs:
            kwargs["id"] = self.id

    @cached(_cache)
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
        self._update_cache(**updated_data)
        updated_data["id"] = self.id

    def __eq__(self, other):
        if isinstance(other, self.__class__):
            return self.id == other.id
        return False

    def __hash__(self):
        return hash(self.id)

    def _update_cache(self, **kwargs):
        for name, value in kwargs.items():
            if name != "id":
                _cache[hashkey(self, name)] = value

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
            try:
                return bool(
                    r.table(cls._rdb_table)
                    .get(document_id)["id"]
                    .run(cls._rdb_connection)
                )
            except:
                return False

    @classmethod
    def get_all(cls):
        """
        Get all documents.

        :return: List of objects.
        :rtype: list
        """
        with cls._rdb_context():
            return [
                cls(document_id)
                for document_id in r.table(cls._rdb_table)["id"].run(
                    cls._rdb_connection
                )
            ]

    @classmethod
    def get_index(cls, values, index, filter=None):
        """
        Get documents with specific index.

        :param values: Array of values
        :type values: list
        :param index: Index name
        :type index: str
        :param filter: Filter
        :type filter: dict
        :return: List of objects.
        :rtype: list
        """
        query = r.table(cls._rdb_table).get_all(r.args(values), index=index)
        query = query.filter(filter) if filter else query
        with cls._rdb_context():
            return [
                cls(document_id) for document_id in query["id"].run(cls._rdb_connection)
            ]

    @classmethod
    def get_compound_index(cls, values, index, filter=None):
        """
        Get documents with compound index

        :param values: Array of values
        :type values: list
        :param index: Index name
        :type index: str
        :param filter: Filter
        :type filter: dict
        :return: List of objects.
        :rtype: list
        """
        query = r.table(cls._rdb_table).get_all(r.args(values), index=index)
        query = query.filter(filter) if filter else query
        with cls._rdb_context():
            return [
                cls(document_id) for document_id in query["id"].run(cls._rdb_connection)
            ]

    @classmethod
    def insert(cls, documents, conflict="error"):
        """
        Insert array of documents.

        :param documents: List of documents
        :type documents: list
        :param conflict: Conflict strategy
        :type conflict: str
        :values conflict: "error", "replace"
        :return: True if inserted or replaced, False otherwise.
        :rtype: bool
        """
        document_dicts = [document.__dict__["id"] for document in documents]
        with cls._rdb_context():
            result = (
                r.table(cls._rdb_table)
                .insert(document_dicts, conflict=conflict)
                .run(cls._rdb_connection)
            )
        return (
            True if result["inserted"] + result["replaced"] == len(documents) else False
        )

    @classmethod
    def insert_or_update(cls, documents):
        """
        Insert or update array of documents.

        :param documents: List of documents
        :type documents: list
        :return: True if inserted or updated, False otherwise.
        :rtype: bool
        """
        return cls.insert(documents, conflict="update")

    @classmethod
    def delete(cls, document_id):
        with cls._rdb_context():
            result = (
                r.table(cls._rdb_table)
                .get(document_id)
                .delete()
                .run(cls._rdb_connection)
            )
            return result["deleted"] > 0
