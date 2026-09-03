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


def test_list_storage_pools_carries_the_physical_measurement(monkeypatch, test_client):
    """The response model is an explicit field list, so a field it does not
    name is dropped in silence. On a thin pool the physical figure is the only
    one an admin can act on -- the filesystem reports the logical size -- so a
    silent drop here would put the wrong number in front of them."""
    jwt = MockJWT()
    usage = {
        "kind": "local-thin",
        "physical_total_bytes": 18630494388224,
        "physical_free_bytes": 18506929315840,
        "filesystem_free_bytes": 91345006592000,
        "source": "dm-status",
    }
    monkeypatch.setattr(
        "api.services.storage_pools.StoragePoolService.get_storage_pools",
        staticmethod(lambda: [{"id": "pool-1", "physical_usage": usage}]),
    )
    response = test_client(url="/storage-pools", jwt=jwt)
    assert response.status_code == 200
    assert response.json()["storage_pools"][0]["physical_usage"] == usage


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
