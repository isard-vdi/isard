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
        "api.services.admin.users.AdminUsersService.owns_user_id",
        staticmethod(lambda payload, user_id: True),
    )
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.user_exists",
        staticmethod(lambda user_id: True),
    )

    response = test_client(url="/admin/item/user/user-1/exists", jwt=jwt)

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
        "api.services.admin.users.AdminUsersService.list_users",
        staticmethod(fake_list),
    )

    response = test_client(url="/admin/items/users", jwt=jwt)

    assert response.status_code == 200
    assert response.json()[0]["id"] == "user-1"
    # Admin role → category_id=None (global listing)
    assert captured["category_id"] is None


def test_admin_list_users_accepts_null_email_verified(monkeypatch, test_client):
    """Pins Bug 37 — DB rows with ``email_verified=None`` must not 500.

    The user table accumulates ``email_verified=None`` for users created
    via paths that skipped the input Pydantic validation (SAML
    auto-register, user migration, direct seeds). Before the fix the
    response model declared ``email_verified: bool | int = False``,
    which Pydantic v2 enforces strictly: the first ``None`` row tripped
    a ResponseValidationError, the route's generic ``except Exception``
    swallowed it, and ``GET /api/v4/admin/users`` 500'd with
    "Failed to list users". The fix widens the union to
    ``bool | int | None = None``.
    """
    jwt = MockJWT()
    stub = [
        # Row 0: never-verified user (legacy DB shape — None).
        {
            "id": "user-legacy",
            "name": "Legacy",
            "provider": "saml",
            "category": "default",
            "uid": "legacy",
            "username": "legacy",
            "role": "user",
            "group": "default-default",
            "email_verified": None,
        },
        # Row 1: password-flow self-verified.
        {
            "id": "user-self",
            "name": "Self",
            "provider": "local",
            "category": "default",
            "uid": "self",
            "username": "self",
            "role": "user",
            "group": "default-default",
            "email_verified": True,
        },
        # Row 2: email-link verified (epoch timestamp).
        {
            "id": "user-link",
            "name": "Link",
            "provider": "local",
            "category": "default",
            "uid": "link",
            "username": "link",
            "role": "user",
            "group": "default-default",
            "email_verified": 1748774400,
        },
    ]
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.list_users",
        staticmethod(lambda category_id=None: stub),
    )

    response = test_client(url="/admin/items/users", jwt=jwt)

    assert response.status_code == 200, response.text
    body = response.json()
    assert len(body) == 3
    # The None row survives the response model validation.
    assert body[0]["id"] == "user-legacy"
    assert body[0]["email_verified"] is None
    assert body[1]["email_verified"] is True
    assert body[2]["email_verified"] == 1748774400


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
        "api.services.admin.users.AdminUsersService.create_user",
        staticmethod(fake_create),
    )

    response = test_client(
        url="/admin/item/user",
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


def _raw_user_with_nullable_nested():
    """A users-table row whose ``user_storage`` carries a ``provider_quota``
    that resolves to ``None``. ``AdminUserFullDataResponse`` keeps
    ``user_storage.provider_quota`` as an optional nested object, so a
    naive ``model_dump(mode="json")`` emits ``provider_quota: null``."""
    return {
        "id": "local-default-admin-admin",
        "name": "Administrator",
        "provider": "local",
        "category": "default",
        "uid": "admin",
        "username": "admin",
        "role": "admin",
        "group": "default-default",
        "active": True,
        "secondary_groups": [],
        "email": "admin@isard",
        "accessed": 1700000000.0,
        "email_verified": False,
        "vpn": {"wireguard": {"keys": {"private": "x", "public": "y"}}},
        "user_storage": {},
    }


def test_admin_get_user_raw_roundtrips_through_generated_client(
    monkeypatch, test_client
):
    """Regression: ``GET /admin/user/{id}/raw`` must NOT emit explicit
    ``null`` for nullable nested-object fields. The openapi generated
    client's ``_parse_response`` eagerly does
    ``AdminUserFullDataResponse.from_dict(response.json())`` inside
    ``sync_detailed``; an explicit ``user_storage.provider_quota: null``
    makes the nested ``from_dict(None)`` raise ``TypeError`` — so the
    webapp's ``user_loader`` sees an exception on a 200 and wrongly
    redirects to maintenance. ``exclude_none=True`` keeps those keys
    absent (``UNSET``) so the client parses cleanly."""
    from isardvdi_apiv4_client.models.admin_user_full_data_response import (
        AdminUserFullDataResponse as ClientModel,
    )

    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.owns_user_id",
        staticmethod(lambda payload, user_id: True),
    )
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.get_user_raw",
        staticmethod(lambda user_id: _raw_user_with_nullable_nested()),
    )

    response = test_client(
        url="/admin/item/user/local-default-admin-admin/raw", jwt=jwt
    )

    assert response.status_code == 200
    body = response.json()
    # No explicit nulls for the nullable nested object the client chokes on.
    assert "provider_quota" not in body.get("user_storage", {})
    # The generated client must parse the body without raising — this is
    # exactly what the webapp's user_loader does.
    parsed = ClientModel.from_dict(body)
    assert parsed.id == "local-default-admin-admin"
    assert parsed.role == "admin"


def test_admin_get_user_full_data_roundtrips_through_generated_client(
    monkeypatch, test_client
):
    """Same contract for ``GET /admin/user/{id}`` — it shares
    ``AdminUserFullDataResponse`` and the same serialization path."""
    from isardvdi_apiv4_client.models.admin_user_full_data_response import (
        AdminUserFullDataResponse as ClientModel,
    )

    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.owns_user_id",
        staticmethod(lambda payload, user_id: True),
    )
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.get_user_full_data",
        staticmethod(lambda user_id: _raw_user_with_nullable_nested()),
    )

    response = test_client(url="/admin/item/user/local-default-admin-admin", jwt=jwt)

    assert response.status_code == 200
    parsed = ClientModel.from_dict(response.json())
    assert parsed.id == "local-default-admin-admin"


def test_admin_update_user(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_update(payload, user_id, data):
        captured["user_id"] = user_id
        captured["data"] = data

    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.update_user",
        staticmethod(fake_update),
    )

    response = test_client(
        url="/admin/item/user/user-1",
        method="PUT",
        body={"name": "Updated Name", "active": True},
        jwt=jwt,
    )

    assert response.status_code == 204
    assert captured["user_id"] == "user-1"
    # The route forwards the validated body via AdminUserUpdateData
    # (model_dump(exclude_none=True)). The previous "ids" injection
    # was dead — update_user never read it.
    assert captured["data"]["name"] == "Updated Name"
    assert captured["data"]["active"] is True
    assert "ids" not in captured["data"]


# ─── Role-elevation guard (runs the real service, stubs only its DB deps) ──


def _stub_update_deps(monkeypatch, target_role="user", target_category="cat-a"):
    monkeypatch.setattr(
        "api.services.admin.users.Caches.get_document",
        staticmethod(
            lambda table, _id: {
                "category": target_category,
                "role": target_role,
                "name": _id,
            }
        ),
    )
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.owns_user_id",
        staticmethod(lambda *a, **k: None),
    )
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.owns_category_id",
        staticmethod(lambda *a, **k: None),
    )
    # The PUT /admin/item/user/{user_id} route dependency calls the
    # common-lib helper, so bypass it there too.
    monkeypatch.setattr(
        "isardvdi_common.helpers.helpers.Helpers.owns_user_id",
        staticmethod(lambda *a, **k: True),
    )
    monkeypatch.setattr(
        "api.services.admin.users.CommonUsers.update_user",
        staticmethod(lambda *a, **k: None),
    )
    monkeypatch.setattr(
        "api.services.admin.users.CommonUsers.update_multiple_users",
        staticmethod(lambda *a, **k: None),
    )
    monkeypatch.setattr("api.routes.users.clear_users_list_cache", lambda *a, **k: None)


def test_admin_update_user_blocks_role_elevation(monkeypatch, test_client):
    _stub_update_deps(monkeypatch)
    response = test_client(
        url="/admin/item/user/u-victim",
        method="PUT",
        body={"role": "admin"},
        jwt=MockJWT(role_id="manager", user_id="u-mgr", category_id="default"),
    )
    assert response.status_code == 403


def test_admin_update_user_allows_lateral_grant(monkeypatch, test_client):
    _stub_update_deps(monkeypatch)
    response = test_client(
        url="/admin/item/user/u-victim",
        method="PUT",
        body={"role": "manager"},
        jwt=MockJWT(role_id="manager", user_id="u-mgr", category_id="default"),
    )
    assert response.status_code == 204


def test_admin_update_user_blocks_self_role_change(monkeypatch, test_client):
    _stub_update_deps(monkeypatch, target_role="admin")
    response = test_client(
        url="/admin/item/user/u-admin",
        method="PUT",
        body={"role": "manager"},
        jwt=MockJWT(role_id="admin", user_id="u-admin"),
    )
    assert response.status_code == 403


def test_admin_update_user_allows_permitted_role(monkeypatch, test_client):
    _stub_update_deps(monkeypatch)
    response = test_client(
        url="/admin/item/user/u-victim",
        method="PUT",
        body={"role": "advanced"},
        jwt=MockJWT(role_id="manager", user_id="u-mgr", category_id="default"),
    )
    assert response.status_code == 204


def test_admin_update_users_bulk_blocks_role_elevation(monkeypatch, test_client):
    _stub_update_deps(monkeypatch)
    response = test_client(
        url="/admin/items/users/bulk",
        method="PUT",
        body={"ids": ["u-victim"], "role": "admin"},
        jwt=MockJWT(role_id="manager", user_id="u-mgr", category_id="default"),
    )
    assert response.status_code == 403


# DELETE /admin/user takes a body (AdminUserDeleteData). The
# ``test_client`` fixture forwards the body via ``client.request("DELETE",
# ..., json=...)`` so it works fine; the previous skip note was
# stale.


def test_admin_delete_users_runs_bulk_deletion_after_response(monkeypatch, test_client):
    """Pins the SIGSEGV remediation for ``services/admin/users.py:331``.

    The previous implementation fired ``gevent.spawn(process_bulk_delete)``
    inside an ``async def`` route — the spawned greenlet was queued on
    a libev Hub that the asyncio worker never drives, so the bulk
    deletion silently never ran (and could trigger a libev UAF SIGSEGV
    under concurrent load). The fix routes the work through
    ``BackgroundTasks``; FastAPI's test client runs the task after the
    response is flushed, so the inner ``CommonUsers.delete_user`` MUST
    have been called by the time ``response = test_client(...)``
    returns.

    Asserting that ``delete_user`` was called proves the asyncio path
    actually executed the work — the test would fail on the prior
    ``gevent.spawn`` implementation because the greenlet's queued
    callback never fires inside the asyncio TestClient.
    """
    jwt = MockJWT()

    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.owns_user_id",
        staticmethod(lambda payload, user_id: True),
    )
    monkeypatch.setattr(
        "api.services.admin.users.CommonUsers.get_user",
        staticmethod(
            lambda user_id: {
                "id": user_id,
                "username": user_id,
                "group": "default-other",
                "category": "default",
            }
        ),
    )
    deleted_args = []
    monkeypatch.setattr(
        "api.services.admin.users.CommonUsers.delete_user",
        staticmethod(
            lambda user_id, agent_id, delete_user: deleted_args.append(
                (user_id, agent_id, delete_user)
            )
        ),
    )
    monkeypatch.setattr(
        "isardvdi_common.connections.api_sessions.revoke_user_session",
        lambda user_id: None,
    )
    # ``revoke_user_session`` is imported into the service module; the
    # module-local binding must also be patched.
    monkeypatch.setattr(
        "api.services.admin.users.revoke_user_session",
        lambda user_id: None,
    )
    monkeypatch.setattr(
        "api.routes.users.clear_users_list_cache",
        lambda: None,
    )

    response = test_client(
        url="/admin/items/users",
        method="DELETE",
        body={"user": ["user-a", "user-b"], "delete_user": True},
        jwt=jwt,
    )

    assert response.status_code == 200, response.text
    # The BackgroundTasks-scheduled work must have run by the time the
    # TestClient returns. Prior gevent.spawn implementation would leave
    # this list empty.
    assert deleted_args == [
        ("user-a", "local-default-admin-admin", True),
        ("user-b", "local-default-admin-admin", True),
    ]


def test_admin_update_users_bulk_runs_after_response(monkeypatch, test_client):
    """Pins the SIGSEGV remediation for ``_common/lib/users/users/user.py:1164``.

    Previously ``CommonUsers.update_multiple_users_th`` fired
    ``gevent.spawn(cls.update_multiple_users, …)``; under apiv4's
    asyncio worker the spawned greenlet never ran and the bulk update
    silently no-op'd. The fix removes the ``_th`` wrapper from
    ``_common`` and the apiv4 service schedules the call via
    ``BackgroundTasks``. The inner ``update_multiple_users`` MUST
    have been called by the time the TestClient returns.
    """
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.owns_user_id",
        staticmethod(lambda payload, user_id: True),
    )
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.owns_category_id",
        staticmethod(lambda payload, category_id: True),
    )
    monkeypatch.setattr(
        "api.services.admin.users.Caches.get_document",
        staticmethod(lambda table, item_id: {"id": item_id, "category": "default"}),
    )
    monkeypatch.setattr(
        "api.services.admin.users.CommonMigrations.enable_users_check",
        staticmethod(lambda active, payload, user=None: None),
    )
    update_calls = []
    monkeypatch.setattr(
        "api.services.admin.users.CommonUsers.update_multiple_users",
        classmethod(
            lambda cls, user_ids, data, batch_id=None, payload=None: update_calls.append(
                (tuple(user_ids), data.get("active"))
            )
        ),
    )
    monkeypatch.setattr(
        "api.routes.users.clear_users_list_cache",
        lambda: None,
    )

    response = test_client(
        url="/admin/items/users/bulk",
        method="PUT",
        body={"ids": ["user-a", "user-b"], "active": False},
        jwt=jwt,
    )

    assert response.status_code == 204, response.text
    assert update_calls == [(("user-a", "user-b"), False)]


def test_admin_migrate_user_runs_migration_after_response(monkeypatch, test_client):
    """Pins the SIGSEGV remediation for ``services/admin/users.py:1159``.

    Same shape as the bulk-delete test: the prior code fired
    ``gevent.spawn(migrate_and_invalidate)`` and the migration silently
    didn't happen under asyncio. The fix uses ``BackgroundTasks`` —
    the inner ``CommonMigrations.process_migrate_user`` must run by the
    time the TestClient returns.
    """
    jwt = MockJWT()

    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.owns_user_id",
        staticmethod(lambda payload, user_id: True),
    )
    monkeypatch.setattr(
        "api.services.admin.users.CommonMigrations.check_valid_migration",
        staticmethod(lambda user_id, target_user_id: []),
    )
    migrated_args = []
    monkeypatch.setattr(
        "api.services.admin.users.CommonMigrations.process_migrate_user",
        staticmethod(
            lambda user_id, target_user_id: migrated_args.append(
                (user_id, target_user_id)
            )
        ),
    )
    monkeypatch.setattr(
        "api.routes.users.clear_users_list_cache",
        lambda: None,
    )
    # ``clear_templates_cache`` is imported into admin/users at module
    # load; the module-local binding must also be patched so the
    # background task doesn't hit a real cache from another test.
    monkeypatch.setattr(
        "api.services.admin.users.clear_templates_cache",
        lambda: None,
    )

    response = test_client(
        url="/admin/item/user/migrate/user-src/user-dst",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200, response.text
    assert migrated_args == [("user-src", "user-dst")]


def test_admin_user_logout(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.force_logout_user",
        staticmethod(lambda payload, user_id: calls.append(user_id)),
    )

    response = test_client(
        url="/admin/item/user/user-1/logout",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 204
    assert calls == ["user-1"]


# ─── Admin groups CRUD ───────────────────────────────────────────────────


def test_admin_list_groups(monkeypatch, test_client):
    jwt = MockJWT()
    stub = [
        {
            "id": "group-1",
            "name": "Group 1",
            "parent_category": "cat-1",
            "description": "Test group",
        }
    ]
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.list_groups",
        staticmethod(lambda payload: stub),
    )

    response = test_client(url="/admin/items/groups", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["id"] == "group-1"
    assert body[0]["name"] == "Group 1"
    assert body[0]["parent_category"] == "cat-1"


def test_admin_get_group(monkeypatch, test_client):
    jwt = MockJWT()
    stub = {
        "id": "group-1",
        "name": "Group 1",
        "parent_category": "cat-1",
        "description": "Test",
    }
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.get_group",
        staticmethod(lambda group_id: stub),
    )

    response = test_client(url="/admin/item/group/group-1", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "group-1"
    assert body["name"] == "Group 1"
    assert body["parent_category"] == "cat-1"
    assert body["description"] == "Test"


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
        "api.services.admin.users.AdminUsersService.create_group",
        staticmethod(fake_create),
    )

    response = test_client(
        url="/admin/item/group",
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
        "api.services.admin.users.AdminUsersService.create_group",
        staticmethod(fake_create),
    )

    response = test_client(
        url="/admin/item/group",
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
        "api.services.admin.users.AdminUsersService.delete_group",
        staticmethod(lambda payload, group_id: calls.append(group_id) or {}),
    )

    response = test_client(
        url="/admin/item/group/group-1",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 204
    assert calls == ["group-1"]


# ─── Admin categories CRUD (in admin/users.py) ──────────────────────────


def test_admin_get_category(monkeypatch, test_client):
    jwt = MockJWT()
    stub = {"id": "cat-1", "name": "Category 1"}
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.get_category",
        staticmethod(lambda category_id: stub),
    )

    response = test_client(url="/admin/item/category/cat-1", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "cat-1"
    assert body["name"] == "Category 1"


def test_admin_create_category(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_create(payload, data):
        captured["name"] = data["name"]
        captured["frontend"] = data["frontend"]
        return {"id": "cat-new", "name": data["name"]}

    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.create_category",
        staticmethod(fake_create),
    )

    response = test_client(
        url="/admin/item/category",
        method="POST",
        body={
            "name": "New Cat",
            "description": "Desc",
            "frontend": True,
            "manager_permissions": {},
        },
        jwt=jwt,
    )

    assert response.status_code == 200
    assert captured == {"name": "New Cat", "frontend": True}


def test_admin_delete_category(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.delete_category",
        staticmethod(lambda payload, category_id: calls.append(category_id) or {}),
    )

    response = test_client(
        url="/admin/item/category/cat-1",
        method="DELETE",
        jwt=jwt,
    )

    # Route returns 204 (no body) like every other ``EmptyResponse`` route
    # in admin/users.py.
    assert response.status_code == 204
    assert calls == ["cat-1"]


def _register_claims_token(**overrides):
    """Mint a flat register token like the authentication service's SignRegisterToken."""
    import os
    from datetime import datetime, timedelta, timezone

    import jwt

    claims = {
        "kid": "isardvdi",
        "type": "register",
        "exp": datetime.now(timezone.utc) + timedelta(seconds=60),
        "provider": "saml",
        "user_id": "saml-ext-uid",
        "username": "jdoe",
        "category_id": "default",
        "name": "John Doe",
        "email": "jdoe@example.com",
        "photo": "",
    }
    claims.update(overrides)
    return jwt.encode(claims, os.environ["API_ISARDVDI_SECRET"], algorithm="HS256")


def test_admin_auto_register_uses_register_claims(monkeypatch, test_client):
    """User identity comes from the Register-Claims token, not the auth token."""
    captured = {}
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.auto_register_user",
        staticmethod(
            lambda payload, data: captured.update(payload=payload, data=data)
            or "new-user-id"
        ),
    )
    response = test_client(
        url="/admin/item/user/auto-register",
        method="POST",
        jwt=MockJWT(role_id="admin"),
        headers={"Register-Claims": _register_claims_token()},
        body={"role_id": "advanced", "group_id": "g1"},
    )
    assert response.status_code == 200
    assert captured["payload"]["provider"] == "saml"
    assert captured["payload"]["user_id"] == "saml-ext-uid"
    assert captured["data"]["role_id"] == "advanced"


def test_admin_auto_register_rejects_non_register_token(monkeypatch, test_client):
    """A non-register token in Register-Claims is forbidden."""
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.auto_register_user",
        staticmethod(lambda payload, data: "x"),
    )
    response = test_client(
        url="/admin/item/user/auto-register",
        method="POST",
        jwt=MockJWT(role_id="admin"),
        headers={"Register-Claims": str(MockJWT(role_id="admin"))},
        body={"role_id": "advanced", "group_id": "g1"},
    )
    assert response.status_code == 403


def test_admin_group_enrollment_reset_surfaces_code(monkeypatch, test_client):
    """reset surfaces the new 6-char code under ``code`` (not null)."""
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.update_group_enrollment",
        staticmethod(lambda payload, data: "abc123"),
    )
    response = test_client(
        url="/admin/item/group/enrollment",
        method="POST",
        jwt=MockJWT(role_id="admin"),
        body={"id": "g1", "role": "advanced", "action": "reset"},
    )
    assert response.status_code == 200
    assert response.json() == {"code": "abc123"}


def test_admin_group_enrollment_disable_returns_true_code(monkeypatch, test_client):
    """disable surfaces ``True`` under ``code``."""
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.update_group_enrollment",
        staticmethod(lambda payload, data: True),
    )
    response = test_client(
        url="/admin/item/group/enrollment",
        method="POST",
        jwt=MockJWT(role_id="admin"),
        body={"id": "g1", "role": "advanced", "action": "disable"},
    )
    assert response.status_code == 200
    assert response.json() == {"code": True}


def test_admin_get_templates_returns_array_not_dict(monkeypatch, test_client):
    # Pin the documented array shape so a duplicate route can't shadow it again.
    jwt = MockJWT(role_id="admin")
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.get_admin_templates",
        staticmethod(
            lambda payload: [
                {
                    "id": "t1",
                    "name": "Template One",
                    "icon": None,
                    "user": "u1",
                    "category": "default",
                }
            ]
        ),
    )

    response = test_client(url="/admin/items/templates", jwt=jwt)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body, list)
    assert body == [
        {
            "id": "t1",
            "name": "Template One",
            "icon": None,
            "user": "u1",
            "category": "default",
        }
    ]
