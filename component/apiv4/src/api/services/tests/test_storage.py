# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for StorageService — partial coverage of the simpler dispatch
methods. Heavy DB-walking methods are exercised by routes/tests/.
"""

from unittest.mock import MagicMock, patch

from api.services.storage import StorageService, check_task_priority

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


class TestCheckTaskPriority:
    """The governor's tier resolution is role-blind (normalize_tier never
    demotes by role). The producer must therefore NOT force a non-admin's
    task to ``low`` (which normalize_tier maps to the maintenance lane) —
    a non-admin's resize/create would be shoved behind template copies and
    PSI-deferred. Non-admins get ``default`` (the action's natural tier);
    only admins may pin a priority.
    """

    def test_non_admin_gets_action_default_not_demoted_to_low(self):
        assert check_task_priority(JWT_PAYLOAD_MANAGER, "high") == "default"
        assert check_task_priority(JWT_PAYLOAD_MANAGER, "low") == "default"
        assert check_task_priority(JWT_PAYLOAD_MANAGER, "default") == "default"

    def test_admin_may_pin_priority(self):
        assert check_task_priority(JWT_PAYLOAD_ADMIN, "high") == "high"
        assert check_task_priority(JWT_PAYLOAD_ADMIN, "low") == "low"
        assert check_task_priority(JWT_PAYLOAD_ADMIN, "default") == "default"

    def test_admin_unknown_priority_rejected(self):
        try:
            check_task_priority(JWT_PAYLOAD_ADMIN, "urgent")
            raised = None
        except Exception as exc:
            raised = exc
        assert getattr(raised, "status_code", None) == 400


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
    @patch("api.services.storage.StorageProcessed.get_storage_row")
    def test_returns_raw_rethinkdb_row(self, mock_get_row, mock_get_storage):
        """``get_storage_detail`` queries the storage row directly from
        rethinkdb (bypasses ``dict(storage)``, which crashes on the
        ``RethinkCustomBase`` proxy because ``storage.keys`` resolves
        to ``None`` via ``__getattr__``). Migration moved the rdb query
        to ``StorageProcessed.get_storage_row``; the test now pins the
        new boundary.
        """
        mock_get_storage.return_value = MagicMock()
        row = {"id": "s1", "status": "ready"}
        mock_get_row.return_value = row

        result = StorageService.get_storage_detail(JWT_PAYLOAD_ADMIN, "s1")
        assert result == row
        # Access-control side-effect must run.
        mock_get_storage.assert_called_once_with(JWT_PAYLOAD_ADMIN, "s1")
        mock_get_row.assert_called_once_with("s1")

    @patch("api.services.storage.get_storage")
    @patch("api.services.storage.StorageProcessed.get_storage_row", return_value=None)
    def test_returns_empty_dict_when_row_missing(self, mock_get_row, mock_get_storage):
        """When the row is gone (race / soft-delete), the helper folds
        ``None`` to ``{}`` instead of returning ``None``."""
        mock_get_storage.return_value = MagicMock()
        result = StorageService.get_storage_detail(JWT_PAYLOAD_ADMIN, "s1")
        assert result == {}


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


class TestConvertSetsMaintenanceOnce:
    """``convert`` may only put the disk into maintenance once.

    ``Storage.convert`` opens with ``self.set_maintenance("convert")`` -- every
    action owns that transition in the model. The service was doing it too, and
    ``set_maintenance`` refuses any action outside {create, delete, download}
    unless the storage is ``ready``. So the first call flipped the disk to
    maintenance and the second call raised ``precondition_required``: convert
    could never succeed, and it left the disk stuck in maintenance, unusable.

    Reproduced against a live install: every convert answered
    ``428 ... must be Ready ... It's actual status is maintenance``.
    """

    def test_the_service_leaves_the_transition_to_the_model(self):
        origin = MagicMock(name="origin_storage")
        origin.user_id = "u-1"
        origin.directory_path = "/isard/groups"
        origin.id = "s-1"
        origin.convert.return_value = "task-1"

        with patch("api.services.storage.get_storage", return_value=origin), patch(
            "api.services.storage.Storage"
        ) as storage_cls:
            storage_cls.init_document.return_value = MagicMock(id="s-2")
            StorageService.convert(
                JWT_PAYLOAD_ADMIN,
                storage_id="s-1",
                new_storage_type="qcow2",
                new_storage_status="ready",
                compress=False,
                priority="default",
            )

        assert origin.set_maintenance.call_count == 0, (
            "the service set maintenance itself; Storage.convert sets it too, and "
            "the second call raises precondition_required because the disk is no "
            "longer ready -- convert can never succeed and the disk is left stuck"
        )
        origin.convert.assert_called_once()
