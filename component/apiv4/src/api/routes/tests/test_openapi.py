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
