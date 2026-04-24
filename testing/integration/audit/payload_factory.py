# SPDX-License-Identifier: AGPL-3.0-or-later

"""Generate the smallest valid payload for an OpenAPI requestBody schema.

Used by the audit harness as the fallback when ``frontend_overrides``
has no hand-curated payload for a given route. The goal is **schema
satisfaction**, not realism — produce something Pydantic will accept so
the request reaches the service and surfaces real bugs.

Recursive walker over the spec's ``components.schemas`` tree. Resolves
``$ref``, picks the first enum value, defaults strings to ``"x"`` and
integers to the schema's ``minimum`` (or 1).
"""

from __future__ import annotations

from typing import Any


def gen_path_param_value(param_name: str, scratch: dict) -> Any:
    """Resolve a path-parameter placeholder against the scratch entities.

    Path parameters in the OpenAPI spec are named like ``{user_id}``,
    ``{category_id}``, ``{group_id}``, ``{desktop_id}``, ``{template_id}``,
    ``{media_id}``, ``{deployment_id}``, ``{domain_id}``, ``{kind}``,
    ``{id}``, ``{nav}``, ``{action}``, ``{status}``, etc. The audit
    fixture builds a dict mapping each known param name to a real id
    or a sensible string default; route_filter skips routes whose
    params can't be resolved.
    """
    return scratch.get(param_name, "x")


def gen_sample(schema: dict, openapi_spec: dict, namespace: str = "audit") -> Any:
    """Return the smallest dict/list/scalar that satisfies ``schema``.

    Resolves ``$ref`` against ``openapi_spec``. Honours ``required`` for
    objects (other fields are omitted, not None). Picks the first
    ``enum`` if available. Falls back to type-default values.
    """
    if not isinstance(schema, dict):
        return None

    # Resolve refs
    if "$ref" in schema:
        schema = _resolve_ref(schema["$ref"], openapi_spec)

    # anyOf / oneOf / allOf — pick the first non-null branch
    for combinator in ("anyOf", "oneOf"):
        if combinator in schema:
            for branch in schema[combinator]:
                if isinstance(branch, dict) and branch.get("type") != "null":
                    return gen_sample(branch, openapi_spec, namespace)
            return None
    if "allOf" in schema:
        merged = {}
        for sub in schema["allOf"]:
            sub = _resolve_ref(sub["$ref"], openapi_spec) if "$ref" in sub else sub
            for k, v in sub.items():
                if k == "properties":
                    merged.setdefault("properties", {}).update(v)
                elif k == "required":
                    merged.setdefault("required", []).extend(v)
                else:
                    merged.setdefault(k, v)
        return gen_sample(merged, openapi_spec, namespace)

    if "enum" in schema and schema["enum"]:
        return schema["enum"][0]

    if "default" in schema:
        return schema["default"]

    type_ = schema.get("type")

    if type_ == "object":
        required = set(schema.get("required", []))
        props = schema.get("properties", {})
        out: dict = {}
        for key in required:
            sub_schema = props.get(key, {"type": "string"})
            out[key] = gen_sample(sub_schema, openapi_spec, namespace)
        return out

    if type_ == "array":
        items_schema = schema.get("items", {})
        # Audit only sends an empty list unless minItems > 0
        min_items = schema.get("minItems", 0)
        if min_items > 0 and items_schema:
            return [
                gen_sample(items_schema, openapi_spec, namespace)
                for _ in range(min_items)
            ]
        return []

    if type_ == "string":
        fmt = schema.get("format")
        if fmt == "uuid":
            return "00000000-0000-0000-0000-000000000000"
        if fmt == "date-time":
            return "2026-01-01T00:00:00+00:00"
        if fmt == "email":
            return f"{namespace}@example.com"
        if fmt == "uri" or schema.get("description", "").lower().startswith("url"):
            return "https://example.invalid/x"
        # Honour minLength
        min_len = schema.get("minLength", 1)
        return f"{namespace}_x" if min_len <= 8 else namespace + "_x" * min_len

    if type_ in ("integer", "number"):
        return schema.get("minimum", 1)

    if type_ == "boolean":
        return True

    if type_ == "null":
        return None

    # Unknown / untyped schema — produce an empty dict (FastAPI usually
    # treats untyped requestBody fields as Any).
    return {}


def _resolve_ref(ref: str, spec: dict) -> dict:
    """Resolve ``#/components/schemas/Foo`` against ``spec``."""
    if not ref.startswith("#/"):
        return {}
    parts = ref.lstrip("#/").split("/")
    node = spec
    for part in parts:
        node = node.get(part, {}) if isinstance(node, dict) else {}
    return node if isinstance(node, dict) else {}
