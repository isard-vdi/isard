# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pin the per-endpoint typed error params in the OpenAPI spec."""

import warnings

from api import app
from fastapi.openapi.utils import get_openapi


def _spec():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        return get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
        )


def _ref_name(schema):
    """Return the component name a ``$ref``/``allOf``/``anyOf`` schema points at."""
    if not isinstance(schema, dict):
        return None
    ref = schema.get("$ref")
    if ref:
        return ref.rsplit("/", 1)[-1]
    for branch in schema.get("allOf", []) + schema.get("anyOf", []):
        name = _ref_name(branch)
        if name:
            return name
    return None


def _scalar_type(prop):
    """Return a property's type, ignoring the ``Optional`` null branch."""
    if "type" in prop:
        return prop["type"]
    for branch in prop.get("anyOf", []):
        if branch.get("type") != "null":
            return branch.get("type")
    return None


def _operations(spec):
    for path, item in spec.get("paths", {}).items():
        if not isinstance(item, dict):
            continue
        for method, op in item.items():
            if method in ("get", "post", "put", "delete", "patch"):
                yield path, method, op


# model name -> (status it must appear on, number of operations using it)
_EXPECTED = {
    "PasswordPolicyErrorResponse": ("400", 5),
    "DesktopNameExistsErrorResponse": ("409", 1),
    "DesktopNotBookedErrorResponse": ("428", 2),
    "RecycleBinRestoreErrorResponse": ("404", 1),
}


def test_typed_error_responses_are_wired():
    spec = _spec()
    found: dict[str, list] = {name: [] for name in _EXPECTED}
    leaked: list = []
    for path, method, op in _operations(spec):
        for status, resp in op.get("responses", {}).items():
            schema = (
                resp.get("content", {}).get("application/json", {}).get("schema", {})
            )
            name = _ref_name(schema)
            if name in _EXPECTED:
                found[name].append((method.upper(), path, status))
                if status != _EXPECTED[name][0]:
                    leaked.append((name, status, method.upper(), path))

    assert not leaked, f"Typed error model used at the wrong status: {leaked}"
    for name, (status, count) in _EXPECTED.items():
        assert len(found[name]) == count, (
            f"{name} expected on {count} operation(s) at {status}, "
            f"found {len(found[name])}: {found[name]}"
        )


def test_typed_error_param_field_types():
    schemas = _spec()["components"]["schemas"]

    assert _scalar_type(schemas["PasswordPolicyErrorParams"]["properties"]["num"]) == (
        "integer"
    )
    assert (
        _scalar_type(schemas["DesktopNameExistsErrorParams"]["properties"]["name"])
        == "string"
    )
    assert (
        _scalar_type(schemas["DesktopNameExistsErrorParams"]["properties"]["users"])
        == "array"
    )
    assert (
        _scalar_type(schemas["DesktopNotBookedErrorParams"]["properties"]["start"])
        == "string"
    )
    assert (
        _scalar_type(schemas["RecycleBinRestoreErrorParams"]["properties"]["user"])
        == "string"
    )

    for resp, params_model in [
        ("PasswordPolicyErrorResponse", "PasswordPolicyErrorParams"),
        ("DesktopNameExistsErrorResponse", "DesktopNameExistsErrorParams"),
        ("DesktopNotBookedErrorResponse", "DesktopNotBookedErrorParams"),
        ("RecycleBinRestoreErrorResponse", "RecycleBinRestoreErrorParams"),
    ]:
        params = schemas[resp]["properties"]["params"]
        assert _ref_name(params) == params_model, f"{resp}.params -> {params}"
