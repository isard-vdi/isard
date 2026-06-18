# SPDX-License-Identifier: AGPL-3.0-or-later

import os
import warnings

import pytest

_is_production = os.environ.get("USAGE", "production") == "production"


@pytest.mark.skipif(_is_production, reason="OpenAPI docs disabled in production")
def test_openapi_schema_generates(test_client):
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        response = test_client(url="/api/v4/openapi.json")
    assert response.status_code == 200
    data = response.json()
    assert "paths" in data
    assert "info" in data
    assert data["info"]["title"] == "IsardVDI API"


@pytest.mark.skipif(_is_production, reason="OpenAPI docs disabled in production")
def test_openapi_includes_load_bearing_endpoints(test_client):
    """Regression guard: every endpoint listed here is consumed by an
    external client (frontend, webapp, hypervisor agent, etc.). If the
    route is ever renamed without a deprecation alias, this test fails
    and forces a deliberate decision.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        response = test_client(url="/api/v4/openapi.json")
    paths = set(response.json().get("paths", {}).keys())

    load_bearing = {
        "/api/v4/maintenance/status",
        "/api/v4/item/user/desktops",
        "/api/v4/items/templates",
        "/api/v4/items/desktops",
        "/api/v4/admin/items/users",
        "/api/v4/admin/items/categories",
        "/api/v4/admin/items/hypervisors",
    }
    missing = load_bearing - paths
    assert not missing, f"Missing load-bearing endpoints in OpenAPI: {missing}"


@pytest.mark.skipif(_is_production, reason="OpenAPI docs disabled in production")
def test_openapi_optional_body_references_named_schema(test_client):
    """Optional request bodies must reference a named component schema,
    not an inline anonymous object.

    An inline ``Optional[dict]`` body makes openapi-python-client mint an
    anonymous ``*Type0`` class for the nullable union member (e.g.
    ``AdminDownloadsActionIdBodyType0``). That name churns on every client
    regen and silently breaks Python consumers that import it. Pinning the
    body to the named ``DownloadItem`` schema yields a stable
    ``Union['DownloadItem', None]`` instead.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        response = test_client(url="/api/v4/openapi.json")
    schema = response.json()

    target = next(
        p
        for p in schema["paths"]
        if p.endswith("/admin/item/downloads/{action}/{kind}/{id}")
    )
    body_schema = schema["paths"][target]["post"]["requestBody"]["content"][
        "application/json"
    ]["schema"]

    refs = [body_schema["$ref"]] if "$ref" in body_schema else []
    refs += [b["$ref"] for b in body_schema.get("anyOf", []) if "$ref" in b]

    assert any(
        r.endswith("/DownloadItem") for r in refs
    ), f"downloads action body must reference DownloadItem, got {body_schema}"


def test_openapi_created_responses_match_the_status_returned():
    """A handler that returns 201 must declare 201 on its decorator.

    FastAPI files ``response_model`` under ``status_code``, which defaults to
    200. A handler that hands back ``JSONResponse(..., status_code=201)``
    without saying so documents its body under 200, and the generated clients
    then parse a body only for 200 — so a strict consumer reads ``None`` from
    a perfectly good 201 and never sees the created id.

    Built from ``app.openapi()`` rather than the served route, so it holds in
    production mode too, where the docs endpoints are disabled.
    """
    from api import app

    spec = app.openapi()
    target = next(p for p in spec["paths"] if p.endswith("/item/deployment"))
    responses = spec["paths"][target]["post"]["responses"]

    assert "201" in responses, (
        "create deployment returns 201 but documents "
        f"{sorted(responses)}; generated clients will not parse its body"
    )
    assert "200" not in responses, (
        "create deployment never returns 200; documenting one makes the "
        "generated client parse a status the route cannot emit"
    )


@pytest.mark.skipif(_is_production, reason="OpenAPI docs disabled in production")
def test_openapi_servers_include_apiv4_prefix(test_client):
    """The frontend client expects every operation to live under /api/v4.
    Pin the prefix so a refactor of the FastAPI mount point breaks here
    rather than at runtime."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        response = test_client(url="/api/v4/openapi.json")
    paths = list(response.json().get("paths", {}).keys())
    assert paths, "OpenAPI exposes no paths"
    assert all(
        p.startswith("/api/v4/") for p in paths
    ), f"OpenAPI paths must start with /api/v4/: {[p for p in paths if not p.startswith('/api/v4/')][:5]}"
