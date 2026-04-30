#
#   Copyright © 2025 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Route tests for :mod:`api.routes.admin.downloads`.

Covers the admin downloads endpoints that replaced the T1/admin
``/admin/downloads[/kind|/register|/action/kind/{id}]`` v3_compat shims.
"""

from api.routes.tests.helpers import MockJWT


def test_admin_downloads_overview(monkeypatch, test_client):
    jwt = MockJWT()
    stub = {
        "domains": 2,
        "media": 5,
        "virt_install": 3,
        "videos": 0,
        "viewers": 1,
    }
    monkeypatch.setattr(
        "api.services.admin.downloads.AdminDownloadsService.get_downloads",
        staticmethod(lambda: stub),
    )

    response = test_client(url="/admin/downloads", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_admin_downloads_by_kind(monkeypatch, test_client):
    jwt = MockJWT()
    stub = [
        {"id": "dom-1", "name": "Ubuntu 24.04"},
        {"id": "dom-2", "name": "Debian 12"},
    ]
    captured = {}

    def fake_get_kind(kind, user_id):
        captured["kind"] = kind
        captured["user_id"] = user_id
        return stub

    monkeypatch.setattr(
        "api.services.admin.downloads.AdminDownloadsService.get_downloads_kind",
        staticmethod(fake_get_kind),
    )

    response = test_client(url="/admin/downloads/domains", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub
    assert captured == {"kind": "domains", "user_id": jwt.payload["user_id"]}


def test_admin_downloads_register(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.admin.downloads.AdminDownloadsService.register",
        staticmethod(lambda: calls.append("register")),
    )

    response = test_client(
        url="/admin/downloads/register",
        method="POST",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == ["register"]


def test_admin_downloads_action_for_all(monkeypatch, test_client):
    """POST /admin/downloads/{action}/{kind} triggers the bulk action."""
    jwt = MockJWT()
    captured = {}

    def fake_action(action, kind, user_id, id=None, data=None):
        captured["action"] = action
        captured["kind"] = kind
        captured["user_id"] = user_id
        captured["id"] = id

    monkeypatch.setattr(
        "api.services.admin.downloads.AdminDownloadsService.download_action",
        staticmethod(fake_action),
    )

    response = test_client(
        url="/admin/downloads/download/domains",
        method="POST",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert captured == {
        "action": "download",
        "kind": "domains",
        "user_id": jwt.payload["user_id"],
        "id": None,
    }


def test_admin_downloads_action_for_item(monkeypatch, test_client):
    """POST /admin/downloads/{action}/{kind}/{id} triggers the action
    against a single item."""
    jwt = MockJWT()
    captured = {}

    def fake_action(action, kind, user_id, id=None, data=None):
        captured["action"] = action
        captured["kind"] = kind
        captured["id"] = id

    monkeypatch.setattr(
        "api.services.admin.downloads.AdminDownloadsService.download_action",
        staticmethod(fake_action),
    )

    response = test_client(
        url="/admin/downloads/abort/media/media-1",
        method="POST",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert captured == {"action": "abort", "kind": "media", "id": "media-1"}
