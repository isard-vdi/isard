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

import inspect
import re
from abc import ABC, abstractmethod
from time import time
from typing import Any, Callable, List, Literal, Optional
from uuid import uuid4

from cachetools import TTLCache, cached
from cachetools.keys import hashkey
from pydantic import UUID4, BaseModel, Field, create_model, field_serializer
from pydantic.experimental.missing_sentinel import MISSING
from rethinkdb import r
from rethinkdb.errors import ReqlNonExistenceError

_cache = TTLCache(maxsize=10, ttl=5)


def pydantic_optional(*fields, except_fields: list[str] = []):
    """
    Decorator to make fields optional in a Pydantic model.
    The optional fields will default to `MISSING`.

    - If no fields are specified, all fields will be made optional.
    - If fields are specified, only those fields will be made optional.
    - If except_fields is specified, those fields will remain as they are in the model.
    - If both fields and except_fields are specified, except_fields will take precedence.

    Usage:
    ```python
    # Make all fields optional
    @optional
    class MyModel(BaseModel):
        field1: int    # Optional
        field2: str    # Optional
        field3: float  # Optional

    # Make specific fields optional
    @optional('field1', 'field2')
    class MyModel(BaseModel):
        field1: int    # Optional
        field2: str    # Optional
        field3: float  # Required

    # Make all fields optional except specified ones
    @optional(except_fields=['field1'])
    class MyModel(BaseModel):
        field1: int    # Required
        field2: str    # Optional
        field3: float  # Optional
    ```
    """

    def _create_optional_model(model_cls):
        """Create an optional version of a Pydantic model by making all fields optional"""
        if not (inspect.isclass(model_cls) and issubclass(model_cls, BaseModel)):
            return model_cls

        # Create optional fields for all model fields
        optional_fields = {}
        for name, field in model_cls.model_fields.items():
            # Recursively make nested fields optional
            new_annotation = _make_nested_optional(field.annotation)
            optional_fields[name] = (new_annotation, MISSING)

        # Create new model with optional fields
        return create_model(
            f"{model_cls.__name__}Optional",
            __base__=BaseModel,
            **optional_fields,
        )

    def _make_nested_optional(annotation):
        """Recursively make nested Pydantic models optional at any depth"""
        import types
        from typing import get_args, get_origin

        # Get the origin and args of the annotation
        origin = get_origin(annotation)
        args = get_args(annotation)

        # Handle Union types (e.g., str | None, list[Model] | None)
        if origin is types.UnionType or origin is type(None):
            if args:
                # Process each type in the union recursively
                new_args = []
                for arg in args:
                    new_args.append(_make_nested_optional(arg))

                # Reconstruct the union
                if len(new_args) == 1:
                    return new_args[0] | type(None)
                else:
                    result = new_args[0]
                    for arg in new_args[1:]:
                        result = result | arg
                    return result

        # Handle List types (e.g., list[Model], List[Model])
        elif origin is list or origin is type(list):
            if args:
                # Recursively process the list element type
                element_type = _make_nested_optional(args[0])
                return list[element_type]
            return annotation

        # Handle Dict types (e.g., dict[str, Model], Dict[str, Model])
        elif origin is dict or origin is type(dict):
            if args and len(args) == 2:
                # Recursively process both key and value types
                key_type = _make_nested_optional(args[0])
                value_type = _make_nested_optional(args[1])
                return dict[key_type, value_type]
            return annotation

        # Handle Optional types (e.g., Optional[Model])
        elif origin is type(None):
            return annotation

        # Handle other generic types (e.g., Set, Tuple, etc.)
        elif origin and args:
            # Recursively process all generic arguments
            new_args = tuple(_make_nested_optional(arg) for arg in args)
            try:
                # Try to reconstruct the generic type
                return origin[new_args]
            except (TypeError, AttributeError):
                # If reconstruction fails, return original annotation
                return annotation

        # Handle direct BaseModel types
        elif inspect.isclass(annotation) and issubclass(annotation, BaseModel):
            return _create_optional_model(annotation) | type(None)

        # Return annotation unchanged if it's not a special type
        return annotation

    def dec(_cls):
        optional_fields = {}
        for name, field in _cls.model_fields.items():
            if (not fields or name in fields) and (
                not except_fields or name not in except_fields
            ):
                # Make nested models optional recursively
                new_annotation = _make_nested_optional(field.annotation)
                optional_fields[name] = (new_annotation, MISSING)

        return create_model(
            _cls.__name__,
            __base__=_cls,
            **optional_fields,
        )

    # Decorator used with no parameters
    if fields and inspect.isclass(fields[0]) and issubclass(fields[0], BaseModel):
        cls = fields[0]
        fields = cls.model_fields
        return dec(cls)

    return dec


class PydanticBase(BaseModel):
    """
    Base Pydantic model for RethinkDB documents.

    For tables that can have a non uuid primary key, override the `id` field with the appropriate type.
    """

    id: UUID4 = Field(
        default=uuid4(),
        description="Primary key of the document",
    )

    @field_serializer("id", when_used="json")
    def serialize_id(self, value: UUID4) -> str:
        return str(value)


class _PydanticBlankModel(PydanticBase):
    """
    Fallback Pydantic model to be used when no specific model is defined.

    Allows any field, except for the `id` field which is validated as a UUID4.
    """

    class Config:
        extra = "allow"


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

    _rdb_table_schema: PydanticBase = _PydanticBlankModel

    @property
    @abstractmethod
    def _rdb_connection(self):
        pass

    @property
    @abstractmethod
    def _rdb_table(self):
        pass

    def __init__(self, id):
        if not self.exists(id):
            # Raise a typed Error so route handlers propagate it as a
            # proper 404 instead of wrapping it as 500 via their generic
            # `except Exception`. The @app.exception_handler(ValueError)
            # fallback in apiv4 only fires when the ValueError escapes
            # the route's try/except, which it never does.
            from isardvdi_common.helpers.error_factory import Error

            raise Error(
                "not_found",
                f"Document with id {id} does not exist.",
                description_code="not_found",
            )
        doc = self.get(id)

        # Initialize object with existing document
        self.__dict__["id"] = doc.get("id")
        self._update_cache(**doc)

    @classmethod
    def init_document(cls, *args, **kwargs):
        """
        Old init method kept for compatibility.
        """
        if args:
            kwargs["id"] = doc_id = args[0]
        with cls._rdb_context():
            doc_id = (
                r.table(cls._rdb_table)
                .insert(kwargs, conflict="update")
                .run(cls._rdb_connection)
                .get("generated_keys", [kwargs.get("id")])[0]
            )

        return cls(doc_id)

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

        pydantic_model = self._rdb_table_schema(
            **updated_data,
        )
        updated_data = pydantic_model.model_dump(mode="json", exclude_unset=True)

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
            except ReqlNonExistenceError:
                # Document does not exist — the only "successful absent"
                # case. Any other error (connection, permissions, bad
                # table, ...) must propagate rather than be masked as
                # "not found".
                return False

    @classmethod
    def get(cls, id) -> dict:
        """
        Get a document by it's primary key.
        """
        with cls._rdb_context():
            return r.table(cls._rdb_table).get(id).run(cls._rdb_connection)

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
    def update_document(
        cls,
        doc_id: str,
        update_data: dict,
        *,
        validate: bool = True,
    ) -> bool:
        """
        Update a document by its ID.

        :param doc_id: Document ID
        :param update_data: Document data to update in the form of a dictionary
        :param validate: Whether to validate the data against the pydantic schema
        """
        if validate:
            pydantic_model = cls._rdb_table_schema(**update_data)
            update_data = pydantic_model.model_dump(mode="json", exclude_unset=True)

        with cls._rdb_context():
            result = (
                r.table(cls._rdb_table)
                .get(doc_id)
                .update(update_data)
                .run(cls._rdb_connection)
            )

        return result

    @classmethod
    def insert_document(
        cls,
        insert_data: list[dict] | dict,
        *,
        conflict: Literal["error", "update"] = "error",
        validate: bool = False,  # TODO: default to True
    ) -> bool:
        """
        Update a document by its ID.

        :param insert_data: Document data to insert in the form of a dictionary or a list of dictionaries
        :param conflict: Conflict resolution strategy, default is "error"
        :param validate: Whether to validate the data against the pydantic schema
        """
        if not isinstance(insert_data, list):
            insert_data = [insert_data]

        if validate:
            # TODO: Avoid using this until we updgrade to pydantic 2.12 and models use MISSING: https://github.com/pydantic/pydantic/pull/11883
            insert_data = [
                cls._rdb_table_schema(**data).model_dump(mode="json")
                for data in insert_data
            ]

        with cls._rdb_context():
            result = (
                r.table(cls._rdb_table)
                .insert(insert_data, conflict=conflict)
                .run(cls._rdb_connection)
            )

        return result

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

    @classmethod
    def query_paginated_raw(
        cls,
        start_after: Optional[
            Any
        ] = None,  # cursor-style pagination. This must be the last item accessed of the previous page
        page_size: int = 20,
        sort_order: str = "desc",
        search: Optional[str] = None,
        search_field: str = "name",
        filters: Optional[dict] = None,
        index: Optional[str] = None,
        index_value: Optional[List] = None,
        merge_fn: Optional[Callable[[dict], dict]] = None,
        pluck: Optional[List[str]] = None,
    ) -> List[dict]:

        table = r.table(cls._rdb_table)

        query = table.order_by(index=r.desc(index) if sort_order == "desc" else index)

        if start_after:
            if sort_order == "desc":
                query = query.between(
                    index_value + [r.minval],
                    index_value + [start_after],
                    index=index,
                    right_bound="open",
                )
            else:
                query = query.between(
                    index_value + [start_after],
                    index_value + [r.maxval],
                    index=index,
                    left_bound="open",
                )
        else:
            query = query.between(
                index_value + [r.minval], index_value + [r.maxval], index=index
            )

        if filters:
            query = query.filter(filters)

        if pluck:
            query = query.pluck(*pluck)

        if merge_fn:
            query = query.merge(merge_fn)

        # Search is performed after merging so the term applies to merged data too.
        # re.escape() treats the input as a literal: raw user regex metacharacters
        # can cause ReDoS or crash the query into a body-leaking 500.
        if search:
            query = query.filter(
                lambda row: row[search_field].match(f"(?i){re.escape(search)}")
            )

        # We'll pre-load 5 pages of data
        query = query.limit(page_size * 5)

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def query_count_raw(
        cls,
        search: Optional[str] = None,
        search_field: str = "name",
        filters: Optional[dict] = None,
        index: Optional[str] = None,
        index_value: Optional[List] = None,
        merge_fn: Optional[Callable[[dict], dict]] = None,
    ) -> int:
        table = r.table(cls._rdb_table)

        # Base query
        if index and index_value is not None:
            query = table.between(
                index_value + [r.minval], index_value + [r.maxval], index=index
            )
        else:
            query = table

        # Apply filters
        if filters:
            query = query.filter(filters)

        # Apply merge function (optional transformation, like adding fields), required for search
        if merge_fn:
            query = query.merge(merge_fn)

        # Apply search after merge to include merged fields.
        # re.escape() required: see query_raw() above.
        if search:
            query = query.filter(
                lambda row: row[search_field].match(f"(?i){re.escape(search)}")
            )

        with cls._rdb_context():
            return query.count().run(cls._rdb_connection)
