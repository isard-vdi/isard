# SPDX-License-Identifier: AGPL-3.0-or-later

from api.routes.tests.helpers import MockJWT


def test_get_default_pool(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.storage_pools.StoragePoolService.get_default_storage_pool",
        staticmethod(lambda: {"id": "default", "name": "Default Pool"}),
    )
    response = test_client(url="/storage-pool/default", jwt=jwt)
    assert response.status_code == 200
    assert response.json()["id"] == "default"


def test_list_storage_pools(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.storage_pools.StoragePoolService.get_storage_pools",
        staticmethod(lambda: [{"id": "pool-1", "name": "Pool 1"}]),
    )
    response = test_client(url="/storage-pools", jwt=jwt)
    assert response.status_code == 200
    assert len(response.json()["storage_pools"]) == 1


def test_get_storage_pool(monkeypatch, test_client):
    jwt = MockJWT()
    monkeypatch.setattr(
        "api.services.storage_pools.StoragePoolService.get_storage_pool",
        staticmethod(lambda pool_id: {"id": pool_id, "name": "Test Pool"}),
    )
    response = test_client(url="/storage-pool/pool-1", jwt=jwt)
    assert response.status_code == 200
    assert response.json()["id"] == "pool-1"


def test_check_category_storage_pool_availability(monkeypatch, test_client):
    """POST /storage-pool/check-category-availability — replaces v3
    /admin/storage_pool/check_category_availability shim."""
    jwt = MockJWT()
    captured = {}

    def fake_check(categories, storage_pool_id):
        captured["categories"] = categories
        captured["pool"] = storage_pool_id
        return True

    monkeypatch.setattr(
        "api.services.storage_pools.StoragePoolService.check_category_availability",
        staticmethod(fake_check),
    )

    response = test_client(
        url="/storage-pool/check-category-availability",
        method="POST",
        body={"categories": ["default"], "storage_pool_id": "pool-1"},
        jwt=jwt,
    )

    assert response.status_code == 200
    assert response.json() == {"available": True}
    assert captured == {"categories": ["default"], "pool": "pool-1"}
