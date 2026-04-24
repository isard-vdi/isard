# SPDX-License-Identifier: AGPL-3.0-or-later

import pytest
from api.routes.tests.helpers import MockJWT


@pytest.mark.clear_cache
def test_get_users_in_group(monkeypatch, test_client):
    expected_users = [
        {"id": "user-1", "name": "User One", "username": "userone", "photo": ""},
        {"id": "user-2", "name": "User Two", "username": "usertwo", "photo": ""},
    ]

    monkeypatch.setattr(
        "api.services.groups.GroupsService.get_users_in_group",
        staticmethod(lambda group_id: expected_users),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_domain_id",
        staticmethod(lambda payload, domain_id: domain_id),
    )

    jwt = MockJWT(role_id="advanced")
    response = test_client(
        url="/item/group/test-group-id/get-users",
        jwt=jwt,
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["users"]) == 2
    assert data["users"][0]["id"] == "user-1"


@pytest.mark.clear_cache
def test_get_users_in_group_empty(monkeypatch, test_client):
    """Empty group → empty users list, not 404. Pin the no-users contract."""
    monkeypatch.setattr(
        "api.services.groups.GroupsService.get_users_in_group",
        staticmethod(lambda group_id: []),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_domain_id",
        staticmethod(lambda payload, domain_id: domain_id),
    )
    jwt = MockJWT(role_id="advanced")
    response = test_client(url="/item/group/empty-group/get-users", jwt=jwt)
    assert response.status_code == 200
    assert response.json() == {"users": []}


@pytest.mark.clear_cache
def test_get_users_in_group_forwards_group_id(monkeypatch, test_client):
    """Pin the group_id boundary — service receives the path param verbatim."""
    captured = {}

    def fake(group_id):
        captured["group_id"] = group_id
        return []

    monkeypatch.setattr(
        "api.services.groups.GroupsService.get_users_in_group",
        staticmethod(fake),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_domain_id",
        staticmethod(lambda payload, domain_id: domain_id),
    )
    jwt = MockJWT(role_id="advanced")
    test_client(url="/item/group/g-special-1234/get-users", jwt=jwt)
    assert captured["group_id"] == "g-special-1234"


@pytest.mark.clear_cache
def test_get_users_in_group_rejects_user_role(monkeypatch, test_client):
    """advanced_router rejects role=user."""
    monkeypatch.setattr(
        "api.services.groups.GroupsService.get_users_in_group",
        staticmethod(lambda group_id: []),
    )
    jwt = MockJWT(role_id="user")
    response = test_client(url="/item/group/g1/get-users", jwt=jwt)
    assert response.status_code == 403


@pytest.mark.clear_cache
def test_get_users_in_group_unexpected_error_is_500(monkeypatch, test_client):
    """Uncaught service exceptions must fall through to the route's
    except Exception arm and return 500."""

    def boom(group_id):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(
        "api.services.groups.GroupsService.get_users_in_group",
        staticmethod(boom),
    )
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_domain_id",
        staticmethod(lambda payload, domain_id: domain_id),
    )
    jwt = MockJWT(role_id="advanced")
    response = test_client(url="/item/group/g-err/get-users", jwt=jwt)
    assert response.status_code == 500
