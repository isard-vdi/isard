#
#   Copyright © 2025 Pau Abril Iranzo
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import os

import pytest
from api.routes.tests.helpers import MockJWT

_is_production = os.environ.get("USAGE", "production") == "production"


def test_api_version_success(monkeypatch, test_client):
    monkeypatch.setenv("USAGE", "test-usage")
    response = test_client(
        url="/api/v4",
    )
    assert response.status_code == 200
    assert response.json() == {
        "name": "IsardVDI",
        "api_version": "4.0-alpha1",
        "isardvdi_version": "fastapi",
        "usage": "test-usage",
    }


def test_api_version_missing_usage_env(monkeypatch, test_client):
    monkeypatch.delenv("USAGE", raising=False)
    response = test_client(
        url="/api/v4",
    )
    assert response.status_code == 500
    assert response.json() == {"error": "USAGE environment variable is missing"}


@pytest.mark.skipif(_is_production, reason="debug endpoint disabled in production")
def test_token_router(test_client):
    for role in ["admin", "manager", "advanced", "user"]:
        jwt = MockJWT(role_id=role)
        response = test_client(
            url="/api/v4/test/payload",
            jwt=jwt,
        )

        assert response.status_code == 200
        expected = {**jwt.payload, "session_id": "isardvdi-service"}
        assert response.json() == expected


@pytest.mark.skipif(_is_production, reason="debug endpoint disabled in production")
def test_token_router_no_jwt(test_client):
    response = test_client(
        url="/api/v4/test/payload",
    )

    assert response.status_code == 403


@pytest.mark.skipif(_is_production, reason="debug endpoint disabled in production")
def test_token_router_old_jwt(test_client):
    # Token must expire OUTSIDE the 60-second clock-skew leeway window
    # added in commit b9e644a5f. ``expiration=-10`` falls inside leeway
    # and is treated as still valid; -120s is unambiguously expired.
    jwt = MockJWT(expiration=-120)
    response = test_client(
        url="/api/v4/test/payload",
        jwt=jwt,
    )

    assert response.status_code == 401


# ---------------------------------------------------------------------------
# /item/category/{category_id}/custom_url  (open router — no JWT required)
# ---------------------------------------------------------------------------


@pytest.mark.clear_cache
def test_category_custom_url_returns_url(monkeypatch, test_client):
    """Returns the custom_url_name string for an existing category."""
    monkeypatch.setattr(
        "api.services.categories.CategoryService.get_category_custom_login_url",
        staticmethod(lambda category_id: "my-url"),
    )

    response = test_client(url="/api/v4/item/category/default/custom_url")

    assert response.status_code == 200
    # Returned as a JSON string so the OAS spec matches the wire format
    # and every generated client (`isardvdi_apiv4_client`, vue 3 sdk)
    # can call `response.json()` without crashing. The Flask webapp
    # logout handler still recovers the raw value via `.strip('"')`.
    assert response.json() == "my-url"
    assert response.headers["content-type"].startswith("application/json")


@pytest.mark.clear_cache
def test_category_custom_url_no_jwt_required(monkeypatch, test_client):
    """Endpoint is on the open router — must not require authentication."""
    called = {}

    def fake_get(category_id):
        called["id"] = category_id
        return "public"

    monkeypatch.setattr(
        "api.services.categories.CategoryService.get_category_custom_login_url",
        staticmethod(fake_get),
    )

    # No jwt= passed
    response = test_client(url="/api/v4/item/category/abc123/custom_url")

    assert response.status_code == 200
    assert called["id"] == "abc123"


@pytest.mark.clear_cache
def test_category_custom_url_service_fallback_on_error(monkeypatch, test_client):
    """The service swallows DB errors and returns '/login' — endpoint must surface that."""
    monkeypatch.setattr(
        "api.services.categories.CategoryService.get_category_custom_login_url",
        staticmethod(lambda category_id: "/login"),
    )

    response = test_client(url="/api/v4/item/category/unknown-id/custom_url")

    assert response.status_code == 200
    assert response.json() == "/login"
