# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for StorageService — partial coverage of the simpler dispatch
methods. Heavy DB-walking methods are exercised by routes/tests/.
"""

from unittest.mock import MagicMock, patch

from api.services.storage import StorageService

JWT_PAYLOAD_ADMIN = {
    "user_id": "u-admin",
    "category_id": "default",
    "group_id": "default-default",
    "role_id": "admin",
}

JWT_PAYLOAD_MANAGER = {
    "user_id": "u-mgr",
    "category_id": "cat-mgr",
    "group_id": "g-mgr",
    "role_id": "manager",
}


class TestSetMaintenance:
    @patch("api.services.storage.get_storage")
    def test_forwards_action_and_returns_id(self, mock_get):
        storage = MagicMock(id="s1")
        mock_get.return_value = storage
        result = StorageService.set_maintenance(JWT_PAYLOAD_ADMIN, "s1", "lock")
        storage.set_maintenance.assert_called_once_with("s1", "lock")
        assert result == "s1"


class TestSetReady:
    @patch("api.services.storage.get_storage")
    def test_calls_set_ready(self, mock_get):
        storage = MagicMock(id="s1")
        mock_get.return_value = storage
        result = StorageService.set_ready(JWT_PAYLOAD_ADMIN, "s1")
        storage.set_ready.assert_called_once_with()
        assert result == "s1"


class TestBatchCheckBackingChain:
    @patch("api.services.storage.get_storage")
    def test_iterates_each_id(self, mock_get):
        storage = MagicMock()
        mock_get.return_value = storage
        StorageService.batch_check_backing_chain(JWT_PAYLOAD_ADMIN, ["s1", "s2", "s3"])
        assert mock_get.call_count == 3
        assert storage.check_backing_chain.call_count == 3
        # user_id forwarded for each call
        for call in storage.check_backing_chain.call_args_list:
            assert call.kwargs["user_id"] == "u-admin"


class TestGetStorageDetail:
    @patch("api.services.storage.get_storage")
    @patch("api.services.storage.r")
    @patch("api.services.storage.RethinkSharedConnection")
    def test_returns_raw_rethinkdb_row(self, mock_conn_cls, mock_r, mock_get_storage):
        """``get_storage_detail`` queries the storage row directly from
        rethinkdb (bypasses ``dict(storage)``, which crashes on the
        ``RethinkCustomBase`` proxy because ``storage.keys`` resolves
        to ``None`` via ``__getattr__``).
        """
        mock_get_storage.return_value = MagicMock()
        # Simulate ``r.table("storage").get(id).run(conn)`` returning a row.
        row = {"id": "s1", "status": "ready"}
        mock_r.table.return_value.get.return_value.run.return_value = row
        # Context manager noop.
        mock_conn_cls._rdb_context.return_value.__enter__ = MagicMock()
        mock_conn_cls._rdb_context.return_value.__exit__ = MagicMock()

        result = StorageService.get_storage_detail(JWT_PAYLOAD_ADMIN, "s1")
        assert result == row
        # Access-control side-effect must run.
        mock_get_storage.assert_called_once_with(JWT_PAYLOAD_ADMIN, "s1")


class TestGetAllStoragesWithUuid:
    @patch(
        "api.services.storage.StorageProcessed.get_storages_with_uuid",
        return_value=[],
    )
    def test_admin_sees_all_categories(self, mock_get):
        StorageService.get_all_storages_with_uuid(JWT_PAYLOAD_ADMIN)
        kwargs = mock_get.call_args.kwargs
        assert kwargs["category_id"] is None  # admin → no scoping

    @patch(
        "api.services.storage.StorageProcessed.get_storages_with_uuid",
        return_value=[],
    )
    def test_manager_scoped_to_own_category(self, mock_get):
        StorageService.get_all_storages_with_uuid(JWT_PAYLOAD_MANAGER)
        kwargs = mock_get.call_args.kwargs
        assert kwargs["category_id"] == "cat-mgr"

    @patch(
        "api.services.storage.StorageProcessed.get_storages_with_uuid",
        return_value=[],
    )
    def test_status_filter_forwarded(self, mock_get):
        StorageService.get_all_storages_with_uuid(JWT_PAYLOAD_ADMIN, status="ready")
        assert mock_get.call_args.kwargs["status"] == "ready"
