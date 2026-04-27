#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

# /admin/roles → manager_router in admin/users.py, AdminUsersService.get_roles(payload).
# /admin/role/{id} → admin_router in admin/roles.py, AdminRolesService.get_role(role_id).

from api.routes.tests.helpers import MockJWT

MOCK_ROLES = [
    {"id": "admin", "name": "Administrator", "description": "Full access"},
    {"id": "manager", "name": "Manager", "description": "Category manager"},
    {"id": "advanced", "name": "Advanced", "description": "Advanced user"},
    {"id": "user", "name": "User", "description": "Basic user"},
]


def test_admin_list_roles_returns_available_roles(monkeypatch, test_client):
    """GET /admin/roles returns the roles visible to the caller's role."""
    captured = {}

    def fake_get_roles(payload):
        captured["role_id"] = payload["role_id"]
        return MOCK_ROLES

    monkeypatch.setattr(
        "api.routes.admin.users.AdminUsersService.get_roles",
        staticmethod(fake_get_roles),
    )

    jwt = MockJWT(role_id="admin")
    response = test_client(url="/admin/roles", jwt=jwt)

    assert response.status_code == 200
    data = response.json()
    assert len(data) == 4
    assert {r["id"] for r in data} == {"admin", "manager", "advanced", "user"}
    assert captured["role_id"] == "admin"


def test_admin_list_roles_accessible_to_manager(monkeypatch, test_client):
    """The handler is on manager_router → managers are allowed in."""
    monkeypatch.setattr(
        "api.routes.admin.users.AdminUsersService.get_roles",
        staticmethod(lambda payload: [MOCK_ROLES[2], MOCK_ROLES[3]]),
    )

    jwt = MockJWT(role_id="manager")
    response = test_client(url="/admin/roles", jwt=jwt)

    assert response.status_code == 200
    assert {r["id"] for r in response.json()} == {"advanced", "user"}


def test_admin_list_roles_forbidden_for_basic_user(monkeypatch, test_client):
    """Basic users cannot reach manager_router endpoints."""
    monkeypatch.setattr(
        "api.routes.admin.users.AdminUsersService.get_roles",
        staticmethod(lambda payload: MOCK_ROLES),
    )

    jwt = MockJWT(role_id="user")
    response = test_client(url="/admin/roles", jwt=jwt)

    assert response.status_code == 403


def test_admin_get_role_returns_single(monkeypatch, test_client):
    """GET /admin/role/{id} → AdminRolesService.get_role(role_id) (no payload arg)."""
    captured = {}

    def fake_get_role(role_id):
        captured["target"] = role_id
        return next((r for r in MOCK_ROLES if r["id"] == role_id), None)

    monkeypatch.setattr(
        "api.routes.admin.roles.AdminRolesService.get_role",
        staticmethod(fake_get_role),
    )

    jwt = MockJWT(role_id="admin")
    response = test_client(url="/admin/role/manager", jwt=jwt)

    assert response.status_code == 200
    assert response.json()["id"] == "manager"
    assert response.json()["name"] == "Manager"
    assert captured == {"target": "manager"}


def test_admin_get_role_unknown_returns_404(monkeypatch, test_client):
    """Unknown role returns 404 when service raises Error('not_found')."""
    from api.services.error import Error

    def raise_not_found(role_id):
        raise Error("not_found", "Role not found")

    monkeypatch.setattr(
        "api.routes.admin.roles.AdminRolesService.get_role",
        staticmethod(raise_not_found),
    )

    jwt = MockJWT(role_id="admin")
    response = test_client(url="/admin/role/does-not-exist", jwt=jwt)

    assert response.status_code == 404


def test_admin_list_roles_handles_service_failure(monkeypatch, test_client):
    """Unexpected exceptions surface as 500 internal_server."""

    def boom(payload):
        raise RuntimeError("users table missing")

    monkeypatch.setattr(
        "api.routes.admin.users.AdminUsersService.get_roles",
        staticmethod(boom),
    )

    jwt = MockJWT(role_id="admin")
    response = test_client(url="/admin/roles", jwt=jwt)

    assert response.status_code == 500
    assert response.json().get("error") == "internal_server"
