def _strip_null_unions(node):
    """Recursively remove ``{"type": "null"}`` branches from ``anyOf``/``oneOf``.

    Pydantic v2 emits ``Optional[X]`` as ``anyOf: [X, {"type": "null"}]`` in
    OpenAPI 3.1. ogen rejects that combination for query/path parameters, and
    ``@hey-api/openapi-ts`` has historically stumbled on it too. The parameter
    ``required: false`` flag already encodes optionality for ogen, so stripping
    the null branch yields a spec both generators can consume.
    """
    if isinstance(node, dict):
        for key in ("anyOf", "oneOf"):
            branches = node.get(key)
            if isinstance(branches, list):
                non_null = [
                    b
                    for b in branches
                    if not (isinstance(b, dict) and b.get("type") == "null")
                ]
                if len(non_null) != len(branches):
                    if len(non_null) == 1:
                        merged = dict(non_null[0])
                        for meta_key in ("title", "description", "default"):
                            if meta_key in node and meta_key not in merged:
                                merged[meta_key] = node[meta_key]
                        node.pop(key, None)
                        for meta_key in ("title", "description", "default"):
                            node.pop(meta_key, None)
                        node.update(merged)
                    else:
                        node[key] = non_null
        for value in node.values():
            _strip_null_unions(value)
    elif isinstance(node, list):
        for item in node:
            _strip_null_unions(item)


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
    _strip_null_unions(spec)
    _strip_parameter_titles(spec)

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
