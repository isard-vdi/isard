# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/storage_pools.py``."""

import pytest
from api.schemas.storage_pools import (
    CheckCategoryAvailabilityRequest,
    CheckCategoryAvailabilityResponse,
    StoragePoolByPathRequest,
    StoragePoolCreateRequest,
    StoragePoolListResponse,
    StoragePoolResponse,
    StoragePoolUpdateRequest,
)
from pydantic import ValidationError


class TestStoragePoolCreateRequest:
    _required = {
        "name": "ssd-pool",
        "description": "SSD pool",
        "mountpoint": "/mnt/ssd",
        "enabled": True,
    }

    def test_accepts_required(self):
        r = StoragePoolCreateRequest(**self._required)
        assert r.name == "ssd-pool"
        # categories defaults to [] (NOT None).
        assert r.categories == []

    @pytest.mark.parametrize(
        "missing", ["name", "description", "mountpoint", "enabled"]
    )
    def test_missing_required_rejected(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            StoragePoolCreateRequest(**payload)

    def test_paths_nested_dict(self):
        """paths is a nested {kind: [{...}, ...]} structure."""
        r = StoragePoolCreateRequest(
            **self._required,
            paths={"disk": [{"path": "/d1", "weight": 100}]},
        )
        assert r.paths["disk"][0]["weight"] == 100


class TestStoragePoolUpdateRequest:
    """All Optional — partial update."""

    def test_accepts_empty(self):
        r = StoragePoolUpdateRequest()
        assert r.name is None

    def test_partial_update(self):
        r = StoragePoolUpdateRequest(enabled=False)
        dump = r.model_dump(exclude_none=True)
        assert dump == {"enabled": False}


class TestStoragePoolResponse:
    def test_id_required(self):
        with pytest.raises(ValidationError):
            StoragePoolResponse()

    def test_id_only(self):
        r = StoragePoolResponse(id="pool-1")
        assert r.id == "pool-1"

    def test_full(self):
        r = StoragePoolResponse(
            id="pool-1",
            name="ssd-pool",
            mountpoint="/mnt/ssd",
            enabled=True,
            enabled_virt=True,
            is_default=False,
            categories_names=[{"id": "cat-a", "name": "A"}],
            storages=42,
            hypers=2,
        )
        assert r.storages == 42


class TestStoragePoolListResponse:
    def test_storage_pools_required(self):
        with pytest.raises(ValidationError):
            StoragePoolListResponse()

    def test_accepts_empty(self):
        assert StoragePoolListResponse(storage_pools=[]).storage_pools == []


class TestStoragePoolByPathRequest:
    def test_path_required(self):
        with pytest.raises(ValidationError):
            StoragePoolByPathRequest()


class TestCheckCategoryAvailabilityRequest:
    def test_categories_required(self):
        with pytest.raises(ValidationError):
            CheckCategoryAvailabilityRequest()

    def test_accepts_required(self):
        r = CheckCategoryAvailabilityRequest(categories=["cat-a"])
        assert r.categories == ["cat-a"]
        assert r.storage_pool_id is None


class TestCheckCategoryAvailabilityResponse:
    def test_available_required(self):
        with pytest.raises(ValidationError):
            CheckCategoryAvailabilityResponse()

    def test_accepts_bool(self):
        assert CheckCategoryAvailabilityResponse(available=True).available is True
