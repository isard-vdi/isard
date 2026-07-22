# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ``AdminStorageService.delete_storage`` — the admin
``DELETE /admin/storage/{id}`` flow.

Pins the post-fix behaviour:

- 404 when the storage row does not exist (typed ``Error``, not raw 500).
- 428 (``precondition_required``) when the storage still has child
  storages, with a useful description that names how many children.
- On the happy path, the canonical cascade chain (``Storage.task_delete``)
  is invoked — same chain the user-facing ``DELETE /item/storage/{id}``
  uses — and the returned task_id is forwarded to the route layer.

Regression history: prior to the fix this endpoint called
``StorageProcessed.mark_delete`` which only flipped ``status="Deleting"``;
no worker consumed that status, so the qcow2 file was never unlinked
and any child storages silently became orphans pointing at a row marked
Deleting.
"""

from unittest.mock import MagicMock, patch

import pytest
from api.services.admin.storage import AdminStorageService
from api.services.error import Error

JWT_PAYLOAD_ADMIN = {
    "user_id": "u-admin",
    "category_id": "default",
    "group_id": "default-default",
    "role_id": "admin",
}


class TestAdminDeleteStorageMissing:
    @patch("api.services.admin.storage.Storage")
    def test_raises_typed_not_found_when_storage_missing(self, mock_storage_cls):
        mock_storage_cls.exists.return_value = False
        with pytest.raises(Error) as exc_info:
            AdminStorageService.delete_storage(JWT_PAYLOAD_ADMIN, "missing-id")
        assert exc_info.value.error["description_code"] == "not_found"
        assert "missing-id" in exc_info.value.error["description"]


class TestAdminDeleteStorageWithChildren:
    @patch("api.services.admin.storage.Storage")
    def test_raises_precondition_required_when_children_exist(self, mock_storage_cls):
        mock_storage_cls.exists.return_value = True
        storage_instance = MagicMock()
        storage_instance.children = [MagicMock(), MagicMock(), MagicMock()]
        mock_storage_cls.return_value = storage_instance

        with pytest.raises(Error) as exc_info:
            AdminStorageService.delete_storage(JWT_PAYLOAD_ADMIN, "parent-id")

        assert exc_info.value.error["description_code"] == "storage_has_children"
        # Operator-facing description must explain WHY and quantify the gap.
        assert "3" in exc_info.value.error["description"]
        assert "parent-id" in exc_info.value.error["description"]
        # task_delete MUST NOT fire — otherwise the cascade chain would
        # unlink the parent qcow2 while children still reference it,
        # which is exactly the silent failure mode this guard exists to
        # prevent.
        storage_instance.task_delete.assert_not_called()


class TestAdminDeleteStorageCascade:
    @patch("api.services.admin.storage.Storage")
    def test_invokes_task_delete_with_user_id_when_no_children(self, mock_storage_cls):
        mock_storage_cls.exists.return_value = True
        storage_instance = MagicMock()
        storage_instance.children = []
        storage_instance.task_delete.return_value = "task-uuid-42"
        mock_storage_cls.return_value = storage_instance

        result = AdminStorageService.delete_storage(JWT_PAYLOAD_ADMIN, "leaf-id")

        storage_instance.task_delete.assert_called_once_with("u-admin")
        assert result == "task-uuid-42"

    @patch("api.services.admin.storage.Storage")
    def test_user_id_forwarded_from_payload(self, mock_storage_cls):
        """Pins that the payload's ``user_id`` (not ``role_id`` or any
        other field) is the one passed to task_delete — so the resulting
        Task is attributed to the admin who issued the delete."""
        mock_storage_cls.exists.return_value = True
        storage_instance = MagicMock()
        storage_instance.children = []
        mock_storage_cls.return_value = storage_instance

        payload = {**JWT_PAYLOAD_ADMIN, "user_id": "u-special-admin"}
        AdminStorageService.delete_storage(payload, "leaf-id")

        storage_instance.task_delete.assert_called_once_with("u-special-admin")
