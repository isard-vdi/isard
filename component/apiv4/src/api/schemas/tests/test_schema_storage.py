# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/storage.py``."""

import pytest
from api.schemas.storage import (
    StorageBatchIdsRequest,
    StorageConvertRequest,
    StorageConvertResponse,
    StorageCreateRequest,
    StorageCreateResponse,
    StorageDerivativesResponse,
    StorageDomain,
    StorageItem,
    StorageMaintenanceRequest,
    StorageMoveByPathRequest,
    StorageParentItem,
    StoragePathRequest,
    StoragePriorityResponse,
    StorageReadyResponse,
    StorageRecreateRequest,
    StorageRsyncToPathRequest,
    StorageRsyncToStoragePoolRequest,
    StorageVirtWinRegRequest,
    TaskIdResponse,
)
from pydantic import ValidationError


class TestStorageDomain:
    @pytest.mark.parametrize("missing", ["id", "name"])
    def test_required(self, missing):
        payload = {"id": "d-1", "name": "D"}
        del payload[missing]
        with pytest.raises(ValidationError):
            StorageDomain(**payload)


class TestStorageItem:
    _required = {
        "category": "default",
        "domains": [{"id": "d-1", "name": "D"}],
        "id": "s-1",
        "user_id": "u-1",
        "user_name": "U",
        "actual_size": 1024,
        "virtual_size": 4096,
        "last": 1234567890,
    }

    def test_accepts_required(self):
        s = StorageItem(**self._required)
        assert s.actual_size == 1024
        assert s.domains[0].id == "d-1"

    @pytest.mark.parametrize("missing", list(_required))
    def test_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            StorageItem(**payload)


class TestStorageReadyResponse:
    def test_items_required(self):
        with pytest.raises(ValidationError):
            StorageReadyResponse()

    def test_accepts_empty(self):
        assert StorageReadyResponse(items=[]).items == []


class TestSimpleTaskIdResponses:
    """Three near-identical wrappers — one assertion each is enough."""

    def test_storage_priority_response(self):
        with pytest.raises(ValidationError):
            StoragePriorityResponse()
        assert StoragePriorityResponse(task_id="t-1").task_id == "t-1"

    def test_task_id_response(self):
        with pytest.raises(ValidationError):
            TaskIdResponse()
        assert TaskIdResponse(task_id="t-1").task_id == "t-1"


class TestStorageCreateResponse:
    @pytest.mark.parametrize("missing", ["storage_id", "task_id"])
    def test_required(self, missing):
        payload = {"storage_id": "s-1", "task_id": "t-1"}
        del payload[missing]
        with pytest.raises(ValidationError):
            StorageCreateResponse(**payload)


class TestStorageConvertResponse:
    @pytest.mark.parametrize("missing", ["new_storage_id", "task_id"])
    def test_required(self, missing):
        payload = {"new_storage_id": "s-2", "task_id": "t-1"}
        del payload[missing]
        with pytest.raises(ValidationError):
            StorageConvertResponse(**payload)


class TestStorageDerivativesResponse:
    def test_required(self):
        with pytest.raises(ValidationError):
            StorageDerivativesResponse()


class TestStorageParentItem:
    _required = {"id": "s-1", "status": "ready", "domains": []}

    def test_accepts_required(self):
        p = StorageParentItem(**self._required)
        assert p.parent_id is None

    @pytest.mark.parametrize("missing", ["id", "status", "domains"])
    def test_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            StorageParentItem(**payload)


class TestStorageMaintenanceRequest:
    def test_default_action(self):
        r = StorageMaintenanceRequest()
        assert r.action == "system maintenance"


class TestStorageCreateRequest:
    _required = {
        "usage": "desktop",
        "storage_type": "qcow2",
        "parent": "s-0",
        "size": "10G",
    }

    def test_accepts_required(self):
        r = StorageCreateRequest(**self._required)
        assert r.user_id is None

    @pytest.mark.parametrize("missing", list(_required))
    def test_required(self, missing):
        payload = {k: v for k, v in self._required.items() if k != missing}
        with pytest.raises(ValidationError):
            StorageCreateRequest(**payload)


class TestStorageConvertRequest:
    def test_defaults(self):
        r = StorageConvertRequest(new_storage_type="raw")
        assert r.new_storage_status == "downloadable"
        assert r.compress is False
        assert r.priority == "default"

    def test_new_storage_type_required(self):
        with pytest.raises(ValidationError):
            StorageConvertRequest()


class TestStorageRecreateRequest:
    def test_defaults(self):
        r = StorageRecreateRequest()
        assert r.priority == "default"
        assert r.retry == 0


class TestStorageMoveByPathRequest:
    def test_dest_path_required(self):
        with pytest.raises(ValidationError):
            StorageMoveByPathRequest()

    def test_default_priority(self):
        r = StorageMoveByPathRequest(dest_path="/d")
        assert r.priority == "default"


class TestStorageRsyncToPathRequest:
    def test_destination_path_required(self):
        with pytest.raises(ValidationError):
            StorageRsyncToPathRequest()

    def test_defaults(self):
        r = StorageRsyncToPathRequest(destination_path="/d")
        assert r.bwlimit is None
        assert r.remove_source_file is False


class TestStorageRsyncToStoragePoolRequest:
    def test_destination_pool_required(self):
        with pytest.raises(ValidationError):
            StorageRsyncToStoragePoolRequest()


class TestStorageVirtWinRegRequest:
    def test_registry_patch_required(self):
        with pytest.raises(ValidationError):
            StorageVirtWinRegRequest()

    def test_default_retry(self):
        r = StorageVirtWinRegRequest(registry_patch="HKEY...")
        assert r.retry == 0


class TestStoragePathRequest:
    def test_path_required(self):
        with pytest.raises(ValidationError):
            StoragePathRequest()


class TestStorageBatchIdsRequest:
    def test_ids_required(self):
        with pytest.raises(ValidationError):
            StorageBatchIdsRequest()

    def test_accepts_empty(self):
        r = StorageBatchIdsRequest(ids=[])
        assert r.ids == []
