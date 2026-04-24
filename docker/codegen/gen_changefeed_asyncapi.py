#!/usr/bin/env python3
#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""
Generate an AsyncAPI 3.0 specification for the IsardVDI changefeed service.

Reads ``component/changefeed/src/tables.json`` (the single source of truth for
the set of tables the changefeed publishes) and emits a deterministic YAML
AsyncAPI 3.0 spec at the requested output path.

For the 13 tables with matching Pydantic row models in
``isardvdi_common.models``, the generator introspects
``model.model_fields`` and emits a lightweight, field-by-field JSON schema.
For the remaining 9 tables, it emits a permissive object schema
(``additionalProperties: true``).

The spec is deterministic (``yaml.safe_dump(sort_keys=True)``) so two
invocations produce byte-identical output.
"""

from __future__ import annotations

import argparse
import importlib
import json
import sys
import typing
from pathlib import Path
from types import UnionType
from typing import Any

import yaml
from changefeed_utils import camel as _camel
from pydantic import BaseModel

# Map changefeed table name -> (module basename, class name) inside
# ``isardvdi_common.models``. Only tables that have a concrete Pydantic row
# model are listed here; the rest fall through to the permissive schema.
TABLE_TO_CLASS: dict[str, tuple[str, str]] = {
    "bookings": ("booking", "BookingModel"),
    "boots": ("boots", "BootModel"),
    "categories": ("category", "CategoryModel"),
    "deployments": ("deployment", "DeploymentModel"),
    "domains": ("domain", "DomainModel"),
    "groups": ("group", "GroupModel"),
    "hypervisors": ("hypervisor", "HypervisorModel"),
    "interfaces": ("interfaces", "InterfaceModel"),
    "media": ("media", "MediaModel"),
    "resource_planner": ("planning", "ResourcePlannerModel"),
    "targets": ("targets", "TargetModel"),
    "users": ("user", "UserModel"),
    "videos": ("videos", "VideoModel"),
}


def _row_schema_name(table: str) -> str:
    return f"{_camel(table)}Row"


def _envelope_schema_name(table: str) -> str:
    return f"{_camel(table)}ChangeEnvelope"


def _change_schema_name(table: str) -> str:
    return f"{_camel(table)}Change"


def _try_load_model(module_name: str, class_name: str) -> type[BaseModel]:
    """Import ``isardvdi_common.models.<module_name>.<class_name>``.

    Raises ``RuntimeError`` if the import fails for any reason (e.g. module-level
    side effects like ``IsardViewer()`` at ``models/domain.py``). Failing loud
    forces the caller to fix the offending model or remove the table from
    ``TABLE_TO_CLASS`` rather than silently emitting a permissive schema.
    """
    full_module = f"isardvdi_common.models.{module_name}"
    try:
        module = importlib.import_module(full_module)
        return getattr(module, class_name)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to load {full_module}.{class_name} for table. "
            "Either fix the import-time side effect in the model module "
            "or remove the table from TABLE_TO_CLASS."
        ) from exc


def _type_to_schema(py_type: Any) -> dict[str, Any]:
    """Convert a Python type hint to a JSON schema fragment.

    Only the shallow structure is preserved — complex nested types degrade
    gracefully to ``type: object, additionalProperties: true`` so the AsyncAPI
    spec stays compact and the downstream ``asyncapi generate models python``
    run produces maintainable code.
    """
    origin = typing.get_origin(py_type)
    args = typing.get_args(py_type)

    if origin in (typing.Union, UnionType):
        non_none = [a for a in args if a is not type(None)]
        has_none = len(non_none) < len(args)
        if len(non_none) == 0:
            return {"type": "null"}
        if len(non_none) == 1:
            base = _type_to_schema(non_none[0])
            if has_none:
                return {"oneOf": [base, {"type": "null"}]}
            return base
        variants = [_type_to_schema(a) for a in non_none]
        if has_none:
            variants.append({"type": "null"})
        return {"oneOf": variants}

    if origin in (list, tuple, set, frozenset):
        return {"type": "array"}

    if origin is dict:
        return {"type": "object", "additionalProperties": True}

    if py_type is str:
        return {"type": "string"}
    if py_type is bool:
        return {"type": "boolean"}
    if py_type is int:
        return {"type": "integer"}
    if py_type is float:
        return {"type": "number"}
    if py_type is type(None):
        return {"type": "null"}
    if py_type is Any or py_type is object:
        return {}

    if isinstance(py_type, type) and issubclass(py_type, BaseModel):
        return {"type": "object", "additionalProperties": True}

    # Literal[...] - collapse to the common scalar type
    if origin is typing.Literal:
        scalars = {type(a) for a in args}
        if scalars == {str}:
            return {"type": "string"}
        if scalars == {int}:
            return {"type": "integer"}
        if scalars == {bool}:
            return {"type": "boolean"}
        return {}

    # Fallback for anything exotic (generics, NewType, etc.)
    return {}


def _row_schema_from_model(model_cls: type[BaseModel]) -> dict[str, Any]:
    """Build a row schema from a Pydantic model by iterating ``model_fields``."""
    props: dict[str, Any] = {}
    for field_name, field_info in model_cls.model_fields.items():
        props[field_name] = _type_to_schema(field_info.annotation)

    # The changefeed publisher merges ``{"table": <name>}`` into every row
    # before publishing, so the field is always present on the wire even
    # though it is not declared in the Pydantic row models.
    props.setdefault("table", {"type": "string"})

    return {
        "type": "object",
        "additionalProperties": True,
        "properties": props,
    }


def _permissive_row_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "additionalProperties": True,
        "properties": {
            "table": {"type": "string"},
        },
    }


def _change_schema(row_ref: str) -> dict[str, Any]:
    row = {"$ref": f"#/components/schemas/{row_ref}"}
    nullable_row = {"oneOf": [row, {"type": "null"}]}
    return {
        "type": "object",
        "properties": {
            "new_val": nullable_row,
            "old_val": nullable_row,
        },
    }


def _envelope_schema(table: str, change_ref: str) -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["change", "table"],
        "properties": {
            "table": {
                "type": "string",
                "description": f"Always the literal string '{table}'.",
            },
            "change": {
                "$ref": f"#/components/schemas/{change_ref}",
            },
        },
    }


def build_spec(tables: list[dict[str, Any]]) -> dict[str, Any]:
    channels: dict[str, Any] = {}
    operations: dict[str, Any] = {}
    messages: dict[str, Any] = {}
    schemas: dict[str, Any] = {}

    for entry in tables:
        table_name = entry["table"]
        is_stream = bool(entry.get("stream"))
        camel = _camel(table_name)
        row_name = _row_schema_name(table_name)
        change_name = _change_schema_name(table_name)
        envelope_name = _envelope_schema_name(table_name)

        # Row schema
        if table_name in TABLE_TO_CLASS:
            module_name, class_name = TABLE_TO_CLASS[table_name]
            model = _try_load_model(module_name, class_name)
            schemas[row_name] = _row_schema_from_model(model)
        else:
            schemas[row_name] = _permissive_row_schema()

        # Change + envelope schemas
        schemas[change_name] = _change_schema(row_name)
        schemas[envelope_name] = _envelope_schema(table_name, change_name)

        # Message
        messages[envelope_name] = {
            "name": envelope_name,
            "title": f"{camel} change envelope",
            "payload": {"$ref": f"#/components/schemas/{envelope_name}"},
        }

        # Pubsub channel + operation
        channels[table_name] = {
            "address": table_name,
            "messages": {
                "change": {"$ref": f"#/components/messages/{envelope_name}"},
            },
        }
        operations[f"publish{camel}"] = {
            "action": "send",
            "channel": {"$ref": f"#/channels/{table_name}"},
            "messages": [
                {"$ref": f"#/channels/{table_name}/messages/change"},
            ],
        }

        # Stream channel + operation (only for stream-enabled tables)
        if is_stream:
            stream_key = f"stream_{table_name}"
            channels[stream_key] = {
                "address": f"stream:{table_name}",
                "messages": {
                    "change": {"$ref": f"#/components/messages/{envelope_name}"},
                },
            }
            operations[f"publishStream{camel}"] = {
                "action": "send",
                "channel": {"$ref": f"#/channels/{stream_key}"},
                "messages": [
                    {"$ref": f"#/channels/{stream_key}/messages/change"},
                ],
            }

    return {
        "asyncapi": "3.0.0",
        "info": {
            "title": "IsardVDI Changefeed",
            "version": "1.0.0",
            "description": (
                "Real-time RethinkDB change events published to Redis by the "
                "isard-changefeed service. Each table gets a dedicated channel "
                "(pub/sub) and, for the subset of tables used by the engine and "
                "vpn consumers, an additional ``stream:<table>`` Redis Stream "
                "channel."
            ),
        },
        "servers": {
            "redis": {
                "host": "isard-redis:6379",
                "protocol": "redis",
            },
        },
        "channels": channels,
        "operations": operations,
        "components": {
            "messages": messages,
            "schemas": schemas,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--tables", type=Path, required=True, help="Path to tables.json"
    )
    parser.add_argument(
        "--output", type=Path, required=True, help="Path to output .yaml"
    )
    args = parser.parse_args()

    with args.tables.open("r", encoding="utf-8") as fh:
        tables = json.load(fh)

    spec = build_spec(tables)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8") as fh:
        yaml.safe_dump(spec, fh, sort_keys=True, default_flow_style=False)

    print(f"Wrote AsyncAPI spec ({len(tables)} tables) to {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
