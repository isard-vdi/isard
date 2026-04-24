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
