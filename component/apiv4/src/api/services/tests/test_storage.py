# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for StorageService — partial coverage of the simpler dispatch
methods. Heavy DB-walking methods are exercised by routes/tests/.
"""

from unittest.mock import MagicMock, patch

import pytest
from api.services.error import Error
from api.services.storage import StorageService, check_task_priority
from isardvdi_common.models.task import Task
from rq.exceptions import NoSuchJobError

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


class TestStaleTaskPointer:
    """A storage row can outlive the RQ job it points at (result TTL expiry, a
    redis restart mid-chain, a job deleted while something was still writing
    its status). Building ``Task(storage.task)`` then raises ``NoSuchJobError``
    out of the service and the route turns it into a 500 — on two endpoints
    that both have a good answer available: "no task" and "nothing to abort".

    Both cases below leave the job hash *present but unloadable*, which is the
    documented shape a bare ``Task.exists`` key check waves through — so these
    pin the fetch-tolerant behaviour, not an existence check.
    """

    @staticmethod
    def _unloadable_job():
        """Job hash present (``exists`` says yes) but ``fetch`` cannot load it."""
        return (
            patch("isardvdi_common.models.task.Job.exists", return_value=True),
            patch(
                "isardvdi_common.models.task.Job.fetch",
                side_effect=NoSuchJobError("No such job: t-gone"),
            ),
        )

    @patch("api.services.storage.get_storage")
    def test_get_task_answers_no_task_instead_of_raising(self, mock_get_storage):
        mock_get_storage.return_value = MagicMock(task="t-gone")
        exists, fetch = self._unloadable_job()
        with exists, fetch:
            assert StorageService.get_task(JWT_PAYLOAD_ADMIN, "s1") is None

    @patch("api.services.storage.get_storage")
    def test_get_task_still_serialises_a_live_task(self, mock_get_storage):
        """The tolerant path must not swallow the normal answer."""
        mock_get_storage.return_value = MagicMock(task="t-live")
        job = MagicMock(meta={}, origin="storage.default.default.default")
        with patch("isardvdi_common.models.task.Job.exists", return_value=True), patch(
            "isardvdi_common.models.task.Job.fetch", return_value=job
        ), patch.object(Task, "to_dict", return_value={"id": "t-live"}):
            assert StorageService.get_task(JWT_PAYLOAD_ADMIN, "s1") == {"id": "t-live"}

    @patch("api.services.storage.get_storage")
    def test_abort_operations_is_a_no_op_instead_of_raising(self, mock_get_storage):
        """Same idempotent no-op the method already gives a storage with no
        task: there is no live job to abort and no initiator to own it."""
        storage = MagicMock(task="t-gone")
        mock_get_storage.return_value = storage
        exists, fetch = self._unloadable_job()
        with exists, fetch:
            assert StorageService.abort_operations(JWT_PAYLOAD_MANAGER, "s1") == ""
        storage.abort_operations.assert_not_called()

    @patch("api.services.storage.get_storage")
    def test_abort_operations_still_checks_the_owner_of_a_live_task(
        self, mock_get_storage
    ):
        """The tolerant path must not weaken the ownership gate."""
        mock_get_storage.return_value = MagicMock(task="t-live")
        job = MagicMock(meta={"user_id": "someone-else"}, origin="storage.p.d.default")
        with patch("isardvdi_common.models.task.Job.exists", return_value=True), patch(
            "isardvdi_common.models.task.Job.fetch", return_value=job
        ):
            with pytest.raises(Error) as excinfo:
                StorageService.abort_operations(JWT_PAYLOAD_MANAGER, "s1")
        assert excinfo.value.status_code == 403
