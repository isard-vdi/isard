# SPDX-License-Identifier: AGPL-3.0-or-later
"""Contract tests for the OpenAPI operationId normalization pass.

The raw FastAPI auto-generated operationIds look like
``admin_hypervisor_create_api_v4_admin_hypervisor_post`` — the function
name (``admin_hypervisor_create``) followed by the flattened path and
HTTP method. Every generated client (Python, Go, TS) turns these into
method names; the path+method suffix is pure noise.

``gen_openapi._normalize_operation_ids`` strips the suffix whenever the
stripped stem is unique. Collisions force the original string to be
kept.

These tests run against the *post-normalization* spec produced by
``gen_openapi.write_openapi_json``.
"""

import os
import warnings

import pytest
from api import app
from fastapi.openapi.utils import get_openapi
from gen_openapi import (
    _normalize_operation_ids,
    _strip_null_unions,
    _strip_parameter_titles,
)

_is_production = os.environ.get("USAGE", "production") == "production"


def _normalized_spec():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        spec = get_openapi(
            title=app.title,
            version=app.version,
            openapi_version=app.openapi_version,
            description=app.description,
            routes=app.routes,
        )
    _strip_null_unions(spec)
    _strip_parameter_titles(spec)
    _normalize_operation_ids(spec)
    return spec


def _iter_operations(spec):
    for path, path_item in spec.get("paths", {}).items():
        if not isinstance(path_item, dict):
            continue
        for method, op in path_item.items():
            if method not in ("get", "post", "put", "delete", "patch"):
                continue
            yield path, method, op


@pytest.mark.skipif(_is_production, reason="OpenAPI docs disabled in production")
def test_all_operation_ids_are_unique():
    spec = _normalized_spec()
    seen: dict[str, tuple[str, str]] = {}
    duplicates: list[str] = []
    for path, method, op in _iter_operations(spec):
        oid = op["operationId"]
        if oid in seen:
            prev_path, prev_method = seen[oid]
            duplicates.append(
                f"{oid!r} used by {prev_method.upper()} {prev_path} "
                f"and {method.upper()} {path}"
            )
        seen[oid] = (path, method)
    assert not duplicates, "Duplicate operationIds: " + "; ".join(duplicates)


@pytest.mark.skipif(_is_production, reason="OpenAPI docs disabled in production")
def test_most_operation_ids_are_stripped():
    """At least 95% of operationIds should have the _api_v4 suffix removed.

    Collisions force us to keep the original for some ops, but if too
    many remain untouched the normalizer probably has a bug (wrong
    split token, wrong iteration shape, etc.).
    """
    spec = _normalized_spec()
    total = 0
    still_verbose = 0
    for _, _, op in _iter_operations(spec):
        total += 1
        if "_api_v4" in op["operationId"]:
            still_verbose += 1
    assert total > 0, "spec has no operations — something is very wrong"
    verbose_ratio = still_verbose / total
    assert verbose_ratio < 0.05, (
        f"{still_verbose}/{total} ({verbose_ratio:.1%}) operationIds "
        "still contain '_api_v4'; normalizer likely regressed"
    )
