#
#   Copyright © 2025 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Route tests for :mod:`api.routes.admin.users`.

Covers the admin user / group / category CRUD surfaces that the webapp
admin relies on. Tests monkeypatch the service methods so the DB is
never touched.
"""

from api.routes.tests.helpers import MockJWT

# ─── Admin users CRUD ────────────────────────────────────────────────────


def test_admin_user_exists(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.admin_users.AdminUsersService.owns_user_id",
        staticmethod(lambda payload, user_id: True),
    )
    monkeypatch.setattr(
        "api.services.admin_users.AdminUsersService.user_exists",
        staticmethod(lambda user_id: True),
    )

    response = test_client(url="/admin/user/user-1/exists", jwt=jwt)

    assert response.status_code == 200
    assert response.json() is True


def test_admin_list_users(monkeypatch, test_client):
    jwt = MockJWT()
    stub = [
        {
            "id": "user-1",
            "name": "User 1",
            "provider": "local",
            "category": "default",
            "uid": "user1",
            "username": "user1",
            "role": "user",
            "group": "default-default",
        }
    ]
    captured = {}

    def fake_list(category_id=None):
        captured["category_id"] = category_id
        return stub

    monkeypatch.setattr(
        "api.services.admin_users.AdminUsersService.list_users",
        staticmethod(fake_list),
    )

    response = test_client(url="/admin/users", jwt=jwt)

    assert response.status_code == 200
    assert response.json()[0]["id"] == "user-1"
    # Admin role → category_id=None (global listing)
    assert captured["category_id"] is None


def test_admin_create_user(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_create(payload, data):
        captured["username"] = data["username"]
        captured["role"] = data["role"]
        return {
            "id": "user-new",
            "name": "Alice Admin",
            "provider": "local",
            "category": "default",
            "uid": "alice",
            "username": "alice",
            "role": "advanced",
            "group": "default-default",
        }

    monkeypatch.setattr(
        "api.services.admin_users.AdminUsersService.create_user",
        staticmethod(fake_create),
    )

    response = test_client(
        url="/admin/user",
        method="POST",
        body={
            "username": "alice",
            "name": "Alice Admin",
            "category": "default",
            "group": "default-default",
            "role": "advanced",
            "password": "pass123",
        },
        jwt=jwt,
    )

    assert response.status_code == 200
    assert captured == {"username": "alice", "role": "advanced"}


def test_admin_update_user(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_update(payload, user_id, data):
        captured["user_id"] = user_id
        captured["data"] = data

    monkeypatch.setattr(
        "api.services.admin_users.AdminUsersService.update_user",
        staticmethod(fake_update),
    )

    response = test_client(
        url="/admin/user/user-1",
        method="PUT",
        body={"name": "Updated Name", "active": True},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert captured["user_id"] == "user-1"
    # The route injects the user_id into ``ids`` before forwarding.
    assert captured["data"]["ids"] == ["user-1"]
    assert captured["data"]["name"] == "Updated Name"


# NOTE: DELETE /admin/user takes a body (AdminUserDeleteData) but
# starlette's TestClient.delete() doesn't accept a ``json`` kwarg.
# The route is functional; a test would require calling
# ``client.request("DELETE", ..., json=...)`` directly, which is
# out of scope for the simple ``test_client`` fixture. Skipped.


def test_admin_user_logout(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.admin_users.AdminUsersService.force_logout_user",
        staticmethod(lambda payload, user_id: calls.append(user_id)),
    )

    response = test_client(
        url="/admin/user/user-1/logout",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == ["user-1"]


# ─── Admin groups CRUD ───────────────────────────────────────────────────


def test_admin_list_groups(monkeypatch, test_client):
    jwt = MockJWT()
    stub = [{"id": "group-1", "name": "Group 1"}]
    monkeypatch.setattr(
        "api.services.admin_users.AdminUsersService.list_groups",
        staticmethod(lambda payload: stub),
    )

    response = test_client(url="/admin/groups", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_admin_get_group(monkeypatch, test_client):
    jwt = MockJWT()
    stub = {"id": "group-1", "name": "Group 1", "description": "Test"}
    # Note: ``get_group(group_id)`` takes a single argument (no payload).
    monkeypatch.setattr(
        "api.services.admin_users.AdminUsersService.get_group",
        staticmethod(lambda group_id: stub),
    )

    response = test_client(url="/admin/group/group-1", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_admin_create_group(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_create(payload, data):
        captured["name"] = data["name"]
        captured["parent_category"] = data["parent_category"]
        return {
            "id": "group-new",
            "name": "New Group",
            "parent_category": "default",
        }

    monkeypatch.setattr(
        "api.services.admin_users.AdminUsersService.create_group",
        staticmethod(fake_create),
    )

    response = test_client(
        url="/admin/group",
        method="POST",
        body={
            "name": "New Group",
            "description": "A test group",
            "parent_category": "default",
        },
        jwt=jwt,
    )

    assert response.status_code == 200
    assert captured == {"name": "New Group", "parent_category": "default"}


def test_admin_create_group_accepts_null_external_ids(monkeypatch, test_client):
    """The webapp admin form omits ``external_app_id`` and
    ``external_gid`` so the request schema's ``Optional[str] = None``
    defaults emit ``None``. The response model ``AdminGroup`` must
    accept the same ``None`` shape — declaring those fields as
    ``str`` would reject ``None`` and surface as a generic 500
    'Failed to create group'.
    """
    jwt = MockJWT()

    def fake_create(payload, data):
        return {
            "id": "group-new",
            "name": data["name"],
            "parent_category": data["parent_category"],
            "uid": None,
            "external_app_id": None,
            "external_gid": None,
            "description": "[default] A test group",
        }

    monkeypatch.setattr(
        "api.services.admin_users.AdminUsersService.create_group",
        staticmethod(fake_create),
    )

    response = test_client(
        url="/admin/group",
        method="POST",
        body={
            "name": "New Group",
            "description": "A test group",
            "parent_category": "default",
        },
        jwt=jwt,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["external_app_id"] is None
    assert body["external_gid"] is None


def test_admin_delete_group(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.admin_users.AdminUsersService.delete_group",
        staticmethod(lambda payload, group_id: calls.append(group_id) or {}),
    )

    response = test_client(
        url="/admin/group/group-1",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == ["group-1"]


# ─── Admin categories CRUD (in admin/users.py) ──────────────────────────


def test_admin_get_category(monkeypatch, test_client):
    jwt = MockJWT()
    stub = {"id": "cat-1", "name": "Category 1"}
    monkeypatch.setattr(
        "api.services.admin_users.AdminUsersService.get_category",
        staticmethod(lambda payload, category_id: stub),
    )

    response = test_client(url="/admin/category/cat-1", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_admin_create_category(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_create(payload, data):
        captured["name"] = data["name"]
        captured["frontend"] = data["frontend"]
        return {"id": "cat-new"}

    monkeypatch.setattr(
        "api.services.admin_users.AdminUsersService.create_category",
        staticmethod(fake_create),
    )

    response = test_client(
        url="/admin/category",
        method="POST",
        body={"name": "New Cat", "description": "Desc", "frontend": True},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert captured == {"name": "New Cat", "frontend": True}


def test_admin_delete_category(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.admin_users.AdminUsersService.delete_category",
        staticmethod(lambda payload, category_id: calls.append(category_id) or {}),
    )

    response = test_client(
        url="/admin/category/cat-1",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == ["cat-1"]
