def _strip_parameter_titles(spec: dict) -> None:
    """Remove auto-generated ``title`` fields from inline parameter schemas.

    FastAPI derives a ``title`` from each parameter name (e.g. ``image_type``
    becomes ``"Image Type"``). ogen turns those titles into synthesized Go
    type names, which collide with existing component schemas that share the
    same name. Parameter schemas are referenced by parameter name anyway, so
    the title is pure noise here.
    """
    for path_item in spec.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for operation in path_item.values():
            if not isinstance(operation, dict):
                continue
            for param in operation.get("parameters", []) or []:
                schema = param.get("schema") if isinstance(param, dict) else None
                if isinstance(schema, dict):
                    schema.pop("title", None)


def _strip_nested_schema_titles(node) -> None:
    """Strip ``title`` recursively on every inline sub-schema, stopping at ``$ref``.

    Skips the ``title`` of the node passed in; callers decide whether to
    preserve or drop it. A ``$ref`` dict has no ``properties`` / ``items`` /
    union keys, so recursion terminates naturally at reference boundaries —
    the referent is processed separately as its own ``components/schemas/*``
    entry.
    """
    if not isinstance(node, dict):
        return
    for sub_key in ("items", "additionalProperties", "not"):
        sub = node.get(sub_key)
        if isinstance(sub, dict):
            sub.pop("title", None)
            _strip_nested_schema_titles(sub)
    for list_key in ("allOf", "oneOf", "anyOf", "prefixItems"):
        sub_list = node.get(list_key)
        if isinstance(sub_list, list):
            for sub in sub_list:
                if isinstance(sub, dict):
                    sub.pop("title", None)
                    _strip_nested_schema_titles(sub)
    properties = node.get("properties")
    if isinstance(properties, dict):
        for prop_schema in properties.values():
            if isinstance(prop_schema, dict):
                prop_schema.pop("title", None)
                _strip_nested_schema_titles(prop_schema)


def _strip_component_property_titles(spec: dict) -> None:
    """Remove auto-generated ``title`` fields from inline property sub-schemas.

    FastAPI derives a ``title`` for every field (``params: Dict[str, Any]``
    becomes ``"title": "Params"``). ``openapi-python-client`` uses those
    titles to synthesize class names for inline object sub-schemas, which
    collide globally across the spec (e.g. every request body with a
    ``params`` or ``allowed`` field attempts to generate a ``Params`` /
    ``Allowed`` class). The generator then drops the entire parent schema
    — and every operation that references it — with
    ``Attempted to generate duplicate models with name "..."``.

    The top-level component ``title`` is preserved by this pass (it is the
    public class name when unique); only titles on nested properties /
    items / additionalProperties / anyOf-branches are stripped, since the
    property name already provides a stable identifier. Cross-component
    top-level title collisions are handled separately by
    :func:`_strip_colliding_component_titles`.
    """
    components = spec.get("components", {})
    if not isinstance(components, dict):
        return
    schemas = components.get("schemas", {})
    if not isinstance(schemas, dict):
        return
    for schema in schemas.values():
        if isinstance(schema, dict):
            _strip_nested_schema_titles(schema)


def _strip_colliding_component_titles(spec: dict) -> None:
    """Strip the top-level ``title`` on components sharing a title.

    Pydantic v2 disambiguates schemas that share a short name by prefixing
    the component key with the module path (e.g.
    ``api__schemas__domains__templates__TemplateResponse``) while keeping
    the bare ``title`` (``"TemplateResponse"``). ``openapi-python-client``
    prefers ``title`` over the key, so both components try to generate the
    same class and one is dropped with ``Attempted to generate duplicate
    models with name "..."``.

    Stripping the title on every colliding component forces the generator
    to fall back to the unique key — the generated class name is verbose
    but distinct, and every operation that ``$ref``-ed the dropped schema
    now generates cleanly.
    """
    components = spec.get("components", {})
    if not isinstance(components, dict):
        return
    schemas = components.get("schemas", {})
    if not isinstance(schemas, dict):
        return

    by_title: dict[str, list[str]] = {}
    for key, schema in schemas.items():
        if isinstance(schema, dict):
            title = schema.get("title")
            if isinstance(title, str):
                by_title.setdefault(title, []).append(key)

    for title, keys in by_title.items():
        if len(keys) > 1:
            for key in keys:
                schemas[key].pop("title", None)


def _strip_path_inline_body_titles(spec: dict) -> None:
    """Strip titles on inline request/response body schemas under ``paths``.

    FastAPI titles every ``Body(...)`` payload with the parameter name —
    multiple endpoints accept a generic ``data: dict`` body, all emitted as
    ``"title": "Data"``, which ``openapi-python-client`` promotes to a
    shared class name. Inline bodies carry no ``$ref``, so the generator
    needs to synthesize a name from the operation; stripping the title
    forces that fallback. Schemas reached via ``$ref`` are untouched —
    their referent is a component handled by the other passes.
    """
    for path_item in spec.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for method, op in path_item.items():
            if method not in ("get", "post", "put", "delete", "patch"):
                continue
            if not isinstance(op, dict):
                continue
            bodies = [op.get("requestBody")]
            for resp in (op.get("responses") or {}).values():
                if isinstance(resp, dict):
                    bodies.append(resp)
            for body in bodies:
                content = body.get("content") if isinstance(body, dict) else None
                if not isinstance(content, dict):
                    continue
                for media in content.values():
                    schema = media.get("schema") if isinstance(media, dict) else None
                    if isinstance(schema, dict) and "$ref" not in schema:
                        schema.pop("title", None)
                        _strip_nested_schema_titles(schema)


def _normalize_operation_ids(spec: dict) -> None:
    """Strip the verbose ``_api_v4_<path>_<method>`` suffix FastAPI appends.

    FastAPI generates operationIds of the form
    ``<function_name>_api_v4_<path_flattened>_<method>``. Every client
    generator turns those into method names (``AdminHypervisorCreateApi
    V4AdminHypervisorPost`` in Go, the snake_case equivalent in Python,
    camelCase in TypeScript). The suffix is pure noise; the function
    name alone is descriptive.

    The stripped stem is used only when it is globally unique. If two
    operations would collide (e.g. two FastAPI functions sharing a name
    but bound to different routes), both keep their original verbose id
    — generators are still happy, the collision test stays green.
    """
    ops: list[tuple[dict, str]] = []
    for path_item in spec.get("paths", {}).values():
        if not isinstance(path_item, dict):
            continue
        for method, op in path_item.items():
            if method not in ("get", "post", "put", "delete", "patch"):
                continue
            if not isinstance(op, dict):
                continue
            oid = op.get("operationId")
            if not isinstance(oid, str) or not oid:
                continue
            ops.append((op, oid))

    stem_claims: dict[str, int] = {}
    for _, oid in ops:
        stem = oid.split("_api_v4", 1)[0]
        stem_claims[stem] = stem_claims.get(stem, 0) + 1

    for op, oid in ops:
        stem = oid.split("_api_v4", 1)[0]
        if stem and stem_claims.get(stem, 0) == 1 and stem != oid:
            op["operationId"] = stem


def write_openapi_json(path: str = "/apiv4.json"):
    import json

    from api import app
    from fastapi.openapi.utils import get_openapi

    spec = get_openapi(
        title=app.title,
        version=app.version,
        openapi_version=app.openapi_version,
        description=app.description,
        routes=app.routes,
    )
    _strip_parameter_titles(spec)
    _strip_component_property_titles(spec)
    _strip_colliding_component_titles(spec)
    _strip_path_inline_body_titles(spec)
    _normalize_operation_ids(spec)

    with open(path, "w") as f:
        json.dump(spec, f, indent=2)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Generate APIv4 OpenAPI JSON file.")
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        required=True,
        help="Path to save the OpenAPI JSON file.",
    )

    args = parser.parse_args()
    write_openapi_json(args.output)
