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
        "api.services.admin.users.AdminUsersService.list_users",
        staticmethod(fake_list),
    )

    response = test_client(url="/admin/users", jwt=jwt)

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

    response = test_client(url="/admin/users", jwt=jwt)

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
        "api.services.admin.users.AdminUsersService.update_user",
        staticmethod(fake_update),
    )

    response = test_client(
        url="/admin/user/user-1",
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
        url="/admin/user",
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
        url="/admin/users/bulk",
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
        url="/admin/user/migrate/user-src/user-dst",
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
        url="/admin/user/user-1/logout",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 204
    assert calls == ["user-1"]


# ─── Admin groups CRUD ───────────────────────────────────────────────────


def test_admin_list_groups(monkeypatch, test_client):
    jwt = MockJWT()
    stub = [{"id": "group-1", "name": "Group 1"}]
    monkeypatch.setattr(
        "api.services.admin.users.AdminUsersService.list_groups",
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
        "api.services.admin.users.AdminUsersService.get_group",
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
        "api.services.admin.users.AdminUsersService.create_group",
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
        "api.services.admin.users.AdminUsersService.create_group",
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
        "api.services.admin.users.AdminUsersService.delete_group",
        staticmethod(lambda payload, group_id: calls.append(group_id) or {}),
    )

    response = test_client(
        url="/admin/group/group-1",
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
        "api.services.admin.users.AdminUsersService.create_category",
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
        "api.services.admin.users.AdminUsersService.delete_category",
        staticmethod(lambda payload, category_id: calls.append(category_id) or {}),
    )

    response = test_client(
        url="/admin/category/cat-1",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == ["cat-1"]
