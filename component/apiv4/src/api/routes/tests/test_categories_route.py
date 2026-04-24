# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from api.routes.tests.helpers import MockJWT


@pytest.mark.clear_cache
def test_search_users_in_category_route(monkeypatch, test_client):
    """The /item/category/users/search endpoint is a 4-segment path that
    cannot collide with the 3-segment /item/category/{custom_url} catch-all
    declared on open_router. Before the rename the previous path
    /item/category/search-users was shadowed and returned the wrong handler.
    """
    monkeypatch.setattr(
        "api.services.categories.CategoryService.search_users_in_category",
        staticmethod(lambda category_id, search: []),
    )

    jwt = MockJWT(role_id="advanced", category_id="default")
    response = test_client(
        url="/item/category/users/search?search=test",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"users": []}


@pytest.mark.clear_cache
def test_search_users_in_category_returns_user_list(monkeypatch, test_client):
    """When the service returns hits, the route forwards them under the
    ``users`` key — pin the response shape."""
    # AvailableUser response model requires id/name/username/photo;
    # provide username so model_dump() validates.
    monkeypatch.setattr(
        "api.services.categories.CategoryService.search_users_in_category",
        staticmethod(
            lambda category_id, search: [
                {"id": "u-1", "name": "Alice", "username": "alice"},
                {"id": "u-2", "name": "Anna", "username": "anna"},
            ]
        ),
    )
    jwt = MockJWT(role_id="advanced", category_id="default")
    response = test_client(
        url="/item/category/users/search?search=a",
        jwt=jwt,
    )
    assert response.status_code == 200
    body = response.json()
    assert {u["id"] for u in body["users"]} == {"u-1", "u-2"}


@pytest.mark.clear_cache
def test_search_users_in_category_uses_caller_category(monkeypatch, test_client):
    """The route MUST scope the search to the JWT's category_id, not a
    user-supplied param. Pin the ownership boundary."""
    captured = {}

    def fake_search(category_id, search):
        captured["category_id"] = category_id
        captured["search"] = search
        return []

    monkeypatch.setattr(
        "api.services.categories.CategoryService.search_users_in_category",
        staticmethod(fake_search),
    )
    # Use an explicit category seed so the maintenance lookup performed
    # inside the auth dependency finds a row (otherwise rethinkdb_mock
    # raises TypeError on a None document and the route 500s before
    # reaching the service).
    jwt = MockJWT(role_id="advanced", category_id="cat-mgr")
    test_client(
        url="/item/category/users/search?search=alice",
        jwt=jwt,
        db_tables_data={
            "categories": [
                {"id": "default"},
                {"id": "cat-mgr", "maintenance": False},
            ],
        },
    )
    assert captured == {"category_id": "cat-mgr", "search": "alice"}


@pytest.mark.clear_cache
def test_search_users_in_category_rejects_user_role(monkeypatch, test_client):
    """The endpoint sits on advanced_router, so role=user must not reach it."""
    monkeypatch.setattr(
        "api.services.categories.CategoryService.search_users_in_category",
        staticmethod(lambda category_id, search: []),
    )
    jwt = MockJWT(role_id="user", category_id="default")
    response = test_client(url="/item/category/users/search?search=x", jwt=jwt)
    # advanced_router → 403 for plain users (role check inside dependency)
    assert response.status_code == 403


@pytest.mark.clear_cache
def test_search_users_in_category_missing_search_param_is_400(test_client):
    """`search` is declared Query(..., ...) — required. Omitting it must
    surface a validation error, not a 500 from the service layer. apiv4's
    global RequestValidationError handler returns 400 (not FastAPI's
    default 422) with {"error": "validation_error", ...}."""
    jwt = MockJWT(role_id="advanced", category_id="default")
    response = test_client(url="/item/category/users/search", jwt=jwt)
    assert response.status_code == 400


@pytest.mark.clear_cache
def test_search_users_in_category_unexpected_error_is_500(monkeypatch, test_client):
    """Uncaught service exceptions must fall through to the route's
    except Exception arm and return 500, not leak a 200 with bad content."""

    def boom(category_id, search):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(
        "api.services.categories.CategoryService.search_users_in_category",
        staticmethod(boom),
    )
    jwt = MockJWT(role_id="advanced", category_id="default")
    response = test_client(url="/item/category/users/search?search=x", jwt=jwt)
    assert response.status_code == 500
