# SPDX-License-Identifier: AGPL-3.0-or-later

from api.routes.tests.helpers import MockJWT


def test_get_admin_migration_config(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.migrations.MigrationService.get_admin_migration_config",
        staticmethod(lambda: {"export_enabled": True, "import_enabled": False}),
    )
    response = test_client(
        url="/admin/config/user-migration",
        jwt=jwt,
    )
    assert response.status_code == 200
    body = response.json()
    assert body["export_enabled"] is True
    assert body["import_enabled"] is False


def test_get_admin_migration_config_admin_only(monkeypatch, test_client):
    """admin_router rejects role=user."""
    monkeypatch.setattr(
        "api.services.migrations.MigrationService.get_admin_migration_config",
        staticmethod(lambda: {"export_enabled": True, "import_enabled": True}),
    )
    jwt = MockJWT(role_id="user")
    response = test_client(url="/admin/config/user-migration", jwt=jwt)
    assert response.status_code == 403


def test_update_admin_migration_config(monkeypatch, test_client):
    """PUT /admin/config/user-migration forwards the request body
    (after `model_dump(exclude_none=True)`) to
    MigrationService.update_admin_migration_config. The schema only
    accepts `check_quotas` today — assert that field round-trips.
    """
    captured = {}

    def fake_update(data):
        captured.update(data)
        return {"check_quotas": data.get("check_quotas")}

    monkeypatch.setattr(
        "api.services.migrations.MigrationService.update_admin_migration_config",
        staticmethod(fake_update),
    )
    jwt = MockJWT()
    response = test_client(
        method="PUT",
        url="/admin/config/user-migration",
        body={"check_quotas": True},
        jwt=jwt,
    )
    assert response.status_code == 200
    assert captured == {"check_quotas": True}
    assert response.json() == {"check_quotas": True}


def test_list_user_migration_items(monkeypatch, test_client):
    """GET /item/user-migration/list-items forwards the JWT user_id
    to MigrationService.list_migration_items (str, not payload dict)
    and returns the `items` sub-key of the helper's response."""
    captured = {}

    def fake_list(user_id):
        captured["user_id"] = user_id
        # Route expects {"errors": ..., "items": <MigrationListItemsResponse-shape>}
        # — the response model requires desktops/templates/media/deployments
        # plus action_after_migrate.
        return {
            "errors": None,
            "items": {
                "desktops": [],
                "templates": [],
                "media": [],
                "deployments": [],
                "action_after_migrate": "none",
            },
        }

    monkeypatch.setattr(
        "api.services.migrations.MigrationService.list_migration_items",
        staticmethod(fake_list),
    )
    jwt = MockJWT(user_id="local-default-user-bob")
    response = test_client(url="/item/user-migration/list-items", jwt=jwt)
    assert response.status_code == 200
    body = response.json()
    assert body["desktops"] == []
    assert body["action_after_migrate"] == "none"
    # The route forwarded the caller's user_id from the JWT verbatim.
    assert captured["user_id"] == "local-default-user-bob"


def test_list_user_migration_items_returns_428_when_helper_reports_errors(
    monkeypatch, test_client
):
    """If list_migration_items returns errors (e.g. missing target user),
    the route surfaces them as 428 — pin the contract."""
    monkeypatch.setattr(
        "api.services.migrations.MigrationService.list_migration_items",
        staticmethod(
            lambda user_id: {"errors": ["target_user_missing"], "items": None}
        ),
    )
    jwt = MockJWT()
    response = test_client(url="/item/user-migration/list-items", jwt=jwt)
    assert response.status_code == 428
    assert response.json() == {"errors": ["target_user_missing"]}


# ── migration_router /authentication/{export,import}/{provider} ────────────
#
# These two routes used to be shadowed by token_router copies in
# admin/authentication.py. token_router rejects ``user-migration-required``
# tokens (it requires a regular login), so the migration UI ended up
# unable to query its own provider's export/import flag. Removing the
# token_router shadow let the migration_router handler win — these tests
# pin both that login tokens still work AND that migration tokens now do.


def test_provider_export_enabled_with_login_token(monkeypatch, test_client):
    """Login JWT can read /authentication/export/{provider} via migration_router."""
    monkeypatch.setattr(
        "api.services.config.ConfigService.get_provider_config",
        staticmethod(lambda pid: {"migration": {"export": True, "import": False}}),
    )
    jwt = MockJWT()
    response = test_client(url="/authentication/export/local", jwt=jwt)
    assert response.status_code == 200
    assert response.json() == {"enabled": True}


def test_provider_export_enabled_with_migration_token(monkeypatch, test_client):
    """The shadow-fix: a user-migration-required token can now reach the
    migration_router handler. Before the fix the token_router copy claimed
    the path first and rejected this token type with 403."""
    monkeypatch.setattr(
        "api.services.config.ConfigService.get_provider_config",
        staticmethod(lambda pid: {"migration": {"export": True, "import": False}}),
    )
    jwt = MockJWT(token_type="user-migration-required")
    response = test_client(url="/authentication/export/local", jwt=jwt)
    assert response.status_code == 200
    assert response.json() == {"enabled": True}


def test_provider_export_defaults_to_false_when_unconfigured(monkeypatch, test_client):
    """Provider config without a migration section → enabled=False
    (the route does ``.get('migration', {}).get('export', False)``)."""
    monkeypatch.setattr(
        "api.services.config.ConfigService.get_provider_config",
        staticmethod(lambda pid: {}),
    )
    jwt = MockJWT()
    response = test_client(url="/authentication/export/local", jwt=jwt)
    assert response.status_code == 200
    assert response.json() == {"enabled": False}


def test_provider_import_enabled_with_login_token(monkeypatch, test_client):
    """Sibling route to export, same routing semantics."""
    monkeypatch.setattr(
        "api.services.config.ConfigService.get_provider_config",
        staticmethod(lambda pid: {"migration": {"export": False, "import": True}}),
    )
    jwt = MockJWT()
    response = test_client(url="/authentication/import/google", jwt=jwt)
    assert response.status_code == 200
    assert response.json() == {"enabled": True}


def test_provider_import_enabled_with_migration_token(monkeypatch, test_client):
    """Migration token reaches the import handler too — same shadow-fix."""
    monkeypatch.setattr(
        "api.services.config.ConfigService.get_provider_config",
        staticmethod(lambda pid: {"migration": {"export": False, "import": True}}),
    )
    jwt = MockJWT(token_type="user-migration-required")
    response = test_client(url="/authentication/import/google", jwt=jwt)
    assert response.status_code == 200
    assert response.json() == {"enabled": True}


def test_provider_export_rejects_other_token_types(monkeypatch, test_client):
    """has_migration_required_or_login_token only accepts type in
    {"user-migration-required", "login", ""}. A direct-viewer token
    must not slip through to the migration check."""
    monkeypatch.setattr(
        "api.services.config.ConfigService.get_provider_config",
        staticmethod(lambda pid: {"migration": {"export": True}}),
    )
    jwt = MockJWT(token_type="direct-viewer")
    response = test_client(url="/authentication/export/local", jwt=jwt)
    assert response.status_code == 403
