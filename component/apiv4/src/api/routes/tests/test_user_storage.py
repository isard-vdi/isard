#
#   Copyright © 2025 IsardVDI
#
#   This file is part of IsardVDI.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Route tests for :mod:`api.routes.admin.user_storage`.

Covers the admin user storage endpoints that replaced T1/admin
``/admin/user_storage/*`` v3_compat shims. All handlers live on
``admin_router`` so ``MockJWT()`` is enough; services are
monkeypatched to stay framework-agnostic of the DB.
"""

from api.routes.tests.helpers import MockJWT


def test_admin_user_storage_list(monkeypatch, test_client):
    jwt = MockJWT()
    stub = [
        {"id": "prov-1", "provider": "webdav", "name": "Primary"},
        {"id": "prov-2", "provider": "nextcloud", "name": "Secondary"},
    ]
    monkeypatch.setattr(
        "api.services.admin.user_storage.AdminUserStorageService.list_providers",
        staticmethod(lambda: stub),
    )

    response = test_client(url="/admin/user_storage", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_admin_user_storage_get(monkeypatch, test_client):
    jwt = MockJWT()
    stub = {"id": "prov-1", "provider": "webdav", "name": "Primary"}
    monkeypatch.setattr(
        "api.services.admin.user_storage.AdminUserStorageService.get_provider",
        staticmethod(lambda provider_id: stub),
    )

    response = test_client(url="/admin/user_storage/prov-1", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_admin_user_storage_delete(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.admin.user_storage.AdminUserStorageService.delete_provider",
        staticmethod(lambda provider_id: calls.append(provider_id)),
    )

    response = test_client(
        url="/admin/user_storage/prov-1",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == ["prov-1"]


def test_admin_user_storage_add_basic_auth(monkeypatch, test_client):
    """POST /admin/user_storage/new/auth_basic — replaces v3
    /admin/user_storage/{auth_protocol} shim for basic auth."""
    jwt = MockJWT()
    captured = {}

    def fake_add(
        provider, name, description, url, urlprefix, access, quota, verify_cert
    ):
        captured["provider"] = provider
        captured["name"] = name
        captured["url"] = url
        return "prov-new"

    monkeypatch.setattr(
        "api.services.admin.user_storage.AdminUserStorageService.add_provider_basic_auth",
        staticmethod(fake_add),
    )

    response = test_client(
        url="/admin/user_storage/new/auth_basic",
        method="POST",
        body={
            "provider": "webdav",
            "name": "Primary",
            "description": "Main storage",
            "url": "https://storage.example/remote.php/dav",
            "urlprefix": "/files",
            "access": "rw",
            "quota": None,
            "verify_cert": True,
        },
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"id": "prov-new"}
    assert captured == {
        "provider": "webdav",
        "name": "Primary",
        "url": "https://storage.example/remote.php/dav",
    }


def test_admin_user_storage_reset(monkeypatch, test_client):
    """DELETE /admin/user_storage/{id}/reset — admin reset of a single
    provider."""
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.admin.user_storage.AdminUserStorageService.reset_provider",
        staticmethod(lambda provider_id: calls.append(provider_id)),
    )

    response = test_client(
        url="/admin/user_storage/prov-1/reset",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == ["prov-1"]
