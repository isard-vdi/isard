# SPDX-License-Identifier: AGPL-3.0-or-later

from api.routes.tests.helpers import MockJWT


def test_get_user_ready_storages(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.storage.StorageService.get_user_ready_storages",
        staticmethod(lambda user_id: []),
    )
    response = test_client(url="/items/storage/ready", jwt=jwt)
    assert response.status_code == 200
    assert response.json() == []


def test_get_user_ready_storages_with_data(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.storage.StorageService.get_user_ready_storages",
        staticmethod(lambda user_id: [{"id": "stor-1", "status": "ready"}]),
    )
    response = test_client(url="/items/storage/ready", jwt=jwt)
    assert response.status_code == 200
    assert len(response.json()) == 1


def test_get_storage_detail(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.storage.StorageService.get_storage_detail",
        staticmethod(
            lambda payload, storage_id: {
                "id": storage_id,
                "type": "qcow2",
                "status": "ready",
            }
        ),
    )
    response = test_client(url="/item/storage/test-stor-1", jwt=jwt)
    assert response.status_code == 200
    assert response.json()["id"] == "test-stor-1"


def test_get_storage_parents(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.storage.StorageService.get_parents",
        staticmethod(
            lambda payload, storage_id: [{"id": "parent-1", "status": "ready"}]
        ),
    )
    response = test_client(url="/item/storage/test-stor-1/parents", jwt=jwt)
    assert response.status_code == 200
    assert len(response.json()) == 1


# ─── Admin storage operations (T1 shim replacements) ────────────────────
# Coverage for the T1/storage (~21) and T1/storages (4) shims ported to
# native v4 routes. Admin endpoints accept ``MockJWT()`` (default admin
# role) and are service-monkeypatched.


def test_set_storage_maintenance(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_set_maintenance(payload, storage_id, action):
        captured["storage_id"] = storage_id
        captured["action"] = action
        return storage_id

    monkeypatch.setattr(
        "api.services.storage.StorageService.set_maintenance",
        staticmethod(fake_set_maintenance),
    )

    response = test_client(
        url="/item/storage/stor-1/status/maintenance",
        method="PUT",
        body={"action": "enable"},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"id": "stor-1"}
    assert captured == {"storage_id": "stor-1", "action": "enable"}


def test_set_storage_ready(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.storage.StorageService.set_ready",
        staticmethod(lambda payload, storage_id: storage_id),
    )

    response = test_client(
        url="/item/storage/stor-1/status/ready",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"id": "stor-1"}


def test_get_storage_has_derivatives(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.storage.StorageService.has_derivatives",
        staticmethod(lambda payload, storage_id: 3),
    )

    response = test_client(url="/item/storage/stor-1/has-derivatives", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == {"derivatives": 3}


def test_abort_storage_operations(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_abort(payload, storage_id):
        captured["storage_id"] = storage_id
        return "task-abort-1"

    monkeypatch.setattr(
        "api.services.storage.StorageService.abort_operations",
        staticmethod(fake_abort),
    )

    response = test_client(
        url="/item/storage/stor-1/abort-operations",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"task_id": "task-abort-1"}
    assert captured == {"storage_id": "stor-1"}


def test_sparsify_storage(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_sparsify(payload, storage_id, priority):
        captured["storage_id"] = storage_id
        captured["priority"] = priority
        return "task-sparsify-1"

    monkeypatch.setattr(
        "api.services.storage.StorageService.sparsify",
        staticmethod(fake_sparsify),
    )

    response = test_client(
        url="/item/storage/stor-1/sparsify/priority/low",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"task_id": "task-sparsify-1"}
    assert captured == {"storage_id": "stor-1", "priority": "low"}


def test_stop_storage_desktops(monkeypatch, test_client):
    jwt = MockJWT()
    calls = []
    monkeypatch.setattr(
        "api.services.storage.StorageService.stop_desktops",
        staticmethod(lambda payload, storage_id: calls.append(storage_id) or {}),
    )

    response = test_client(
        url="/item/storage/stor-1/stop",
        method="PUT",
        jwt=jwt,
    )

    assert response.status_code == 200
    assert calls == ["stor-1"]


def test_delete_storage(monkeypatch, test_client):
    jwt = MockJWT()
    captured = {}

    def fake_delete(payload, storage_id):
        captured["storage_id"] = storage_id
        return "task-delete-1"

    monkeypatch.setattr(
        "api.services.storage.StorageService.delete_storage",
        staticmethod(fake_delete),
    )

    response = test_client(
        url="/item/storage/stor-1",
        method="DELETE",
        jwt=jwt,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["message_code"] == "item.queued"
    assert captured == {"storage_id": "stor-1"}


# ─── Admin storage listing (T1/admin/storage* shim replacements) ───────


def test_admin_storage_list(monkeypatch, test_client):
    """GET /admin/storage — replaces v3 /admin/storage shim."""
    jwt = MockJWT()
    stub = [{"id": "stor-1", "status": "ready"}]
    monkeypatch.setattr(
        "api.services.admin_storage.AdminStorageService.get_storages",
        staticmethod(lambda payload, **kwargs: stub),
    )

    response = test_client(url="/admin/storage", jwt=jwt)

    assert response.status_code == 200
    assert response.json() == stub


def test_admin_storage_list_filtered(monkeypatch, test_client):
    """POST /admin/storage with category filter — replaces v3
    /admin/storage/{status} POST shim."""
    jwt = MockJWT()
    captured = {}

    def fake_get(payload, categories=None, status=None):
        captured["categories"] = categories
        captured["status"] = status
        return []

    monkeypatch.setattr(
        "api.services.admin_storage.AdminStorageService.get_storages",
        staticmethod(fake_get),
    )

    response = test_client(
        url="/admin/storage",
        method="POST",
        body={"categories": ["cat-1"]},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert captured == {"categories": ["cat-1"], "status": None}


def test_admin_storage_by_status(monkeypatch, test_client):
    """GET /admin/storage/by-status/{status} — covers the status filter
    path used by the webapp admin table."""
    jwt = MockJWT()
    captured = {}

    def fake_get(payload, status=None, **kwargs):
        captured["status"] = status
        return []

    monkeypatch.setattr(
        "api.services.admin_storage.AdminStorageService.get_storages",
        staticmethod(fake_get),
    )

    response = test_client(url="/admin/storage/by-status/orphan", jwt=jwt)

    assert response.status_code == 200
    assert captured == {"status": "orphan"}


def test_get_storage_ready_wires_real_service(monkeypatch, test_client):
    """GET /items/storage/get-ready — previously a mock on
    open_router returning hard-coded fake data. Now delegates to
    ``StorageService.get_user_ready_storages(user_id)`` which
    mirrors v3 ``api_v3_storage`` + ``get_user_ready_disks`` +
    ``parse_disks``."""
    jwt = MockJWT()
    captured = {}

    def fake_get(user_id):
        captured["user_id"] = user_id
        return [
            {
                "category": "default",
                "domains": [{"id": "d1", "name": "Desktop One"}],
                "id": "storage-1",
                "user_id": user_id,
                "user_name": "admin",
                "actual_size": 1024,
                "virtual_size": 2048,
                "last": 1700000000,
            }
        ]

    monkeypatch.setattr(
        "api.services.storage.StorageService.get_user_ready_storages",
        staticmethod(fake_get),
    )

    response = test_client(url="/items/storage/get-ready", jwt=jwt)
    assert response.status_code == 200
    body = response.json()
    assert captured == {"user_id": jwt.payload["user_id"]}
    assert len(body["items"]) == 1
    assert body["items"][0]["id"] == "storage-1"


def test_increase_storage_size_advanced_router(monkeypatch, test_client):
    """PUT /item/storage/{id}/priority/{p}/increase/{inc} — previously
    a mock on open_router that did nothing. Now wires to
    ``StorageService.increase_size`` which enforces quota, priority
    normalisation and retry validation like v3
    ``storage_increase_size``."""
    jwt = MockJWT(role_id="advanced")
    captured = {}

    def fake_increase(payload, storage_id, increment, priority, retry=0):
        captured["storage_id"] = storage_id
        captured["increment"] = increment
        captured["priority"] = priority
        return "task-inc-1"

    monkeypatch.setattr(
        "api.services.storage.StorageService.increase_size",
        staticmethod(fake_increase),
    )

    response = test_client(
        url="/item/storage/storage-1/priority/low/increase/5",
        method="PUT",
        jwt=jwt,
    )
    assert response.status_code == 200
    assert response.json() == {"task_id": "task-inc-1"}
    assert captured == {
        "storage_id": "storage-1",
        "increment": 5,
        "priority": "low",
    }
