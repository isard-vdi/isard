# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for StorageService — partial coverage of the simpler dispatch
methods. Heavy DB-walking methods are exercised by routes/tests/.
"""

from unittest.mock import MagicMock, create_autospec, patch

from api.services.storage import StorageService, check_task_priority
from isardvdi_common.models.storage import Storage

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
    """The service forwards the ACTION, and nothing else.

    ``Storage.set_maintenance(self, action=..., exclude_domains=None)`` takes the
    action first. Passing the storage id as well binds it to ``action`` and the
    action to ``exclude_domains``: every attached domain is then stamped
    ``current_action = <storage uuid>`` and the exclusion set becomes a set of
    the action string's characters, so it excludes nothing.

    The double is bound to the real signature on purpose. A ``MagicMock``
    accepts any call, so it cannot tell a right call from a wrong one — which is
    why the previous version of this test asserted the wrong order and stayed
    green.
    """

    @staticmethod
    def _storage():
        storage = MagicMock(id="s1")
        # Spec the BOUND method, not the plain function. `Storage.set_maintenance`
        # is unbound, so a stub built from it still expects `self`: it takes
        # `set_maintenance("lock")` and files "lock" under `self`, leaving
        # `action` at its default. `assert_called_once_with("lock")` then passes
        # while `assert_called_once_with(action="lock")` fails — the assertion
        # says "exactly one positional equal to 'lock'", not "the action is
        # 'lock'" — and the day somebody writes the keyword form the stub raises
        # TypeError and turns this red on correct code. Bound, the spec is
        # `(action='system maintenance')` and both forms mean what they say.
        bound = Storage.set_maintenance.__get__(object.__new__(Storage), Storage)
        storage.set_maintenance = create_autospec(bound)
        return storage

    @patch("api.services.storage.get_storage")
    def test_forwards_the_action_and_returns_id(self, mock_get):
        storage = self._storage()
        mock_get.return_value = storage

        result = StorageService.set_maintenance(JWT_PAYLOAD_ADMIN, "s1", "lock")

        storage.set_maintenance.assert_called_once_with("lock")
        assert result == "s1"

    @patch("api.services.storage.get_storage")
    def test_never_passes_the_storage_id(self, mock_get):
        """The regression, stated as the thing that must not happen."""
        storage = self._storage()
        mock_get.return_value = storage

        StorageService.set_maintenance(JWT_PAYLOAD_ADMIN, "s1", "lock")

        (args, kwargs) = storage.set_maintenance.call_args
        assert "s1" not in args and "s1" not in kwargs.values()


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
