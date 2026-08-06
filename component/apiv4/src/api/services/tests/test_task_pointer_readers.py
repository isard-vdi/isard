#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""apiv4's readers of the retired row pointer resolve through the task index.

Both of these also stop being able to 500 on a dangling pointer: the index only
ever names a job that exists, and what it hands back is loaded with the
fetch-tolerant helper rather than constructed blind. ``Task.exists`` would not
have done — a hash left with only a status field passes that check and still
cannot be loaded.
"""

from unittest.mock import MagicMock, patch

import pytest
from api.services.error import Error
from api.services.storage import StorageService

PAYLOAD = {"user_id": "u-1", "category_id": "default", "role_id": "admin"}


class TestGetTask:
    @patch("api.services.storage.get_storage")
    def test_the_current_task_comes_from_the_index(self, mock_get_storage):
        mock_get_storage.return_value = MagicMock(id="disk-1")
        task = MagicMock()
        task.to_dict.return_value = {"id": "t-1"}
        with patch(
            "api.services.storage.current_task_id", return_value="t-1"
        ) as current, patch("api.services.storage.tasks_from_ids", return_value=[task]):
            assert StorageService.get_task(PAYLOAD, "disk-1") == {"id": "t-1"}
        assert current.call_args.args[1] == "disk-1"

    @patch("api.services.storage.get_storage")
    def test_a_row_with_no_live_task_answers_none(self, mock_get_storage):
        mock_get_storage.return_value = MagicMock(id="disk-1")
        with patch("api.services.storage.current_task_id", return_value=None):
            assert StorageService.get_task(PAYLOAD, "disk-1") is None

    @patch("api.services.storage.get_storage")
    def test_an_unloadable_task_answers_none_instead_of_raising(self, mock_get_storage):
        """The index proves the key exists, not that the job loads."""
        mock_get_storage.return_value = MagicMock(id="disk-1")
        with patch("api.services.storage.current_task_id", return_value="t-1"), patch(
            "api.services.storage.tasks_from_ids", return_value=[]
        ):
            assert StorageService.get_task(PAYLOAD, "disk-1") is None


class TestAbortOperations:
    @patch("api.services.storage.get_storage")
    def test_the_owner_check_reads_the_task_the_index_names(self, mock_get_storage):
        storage = MagicMock(id="disk-1")
        mock_get_storage.return_value = storage
        task = MagicMock(user_id="someone-else")
        with patch("api.services.storage.current_task_id", return_value="t-1"), patch(
            "api.services.storage.tasks_from_ids", return_value=[task]
        ):
            with pytest.raises(Error) as excinfo:
                StorageService.abort_operations(
                    {**PAYLOAD, "role_id": "user"}, "disk-1"
                )
        assert excinfo.value.status_code == 403

    @patch("api.services.storage.get_storage")
    def test_nothing_to_abort_is_a_no_op(self, mock_get_storage):
        storage = MagicMock(id="disk-1")
        mock_get_storage.return_value = storage
        with patch("api.services.storage.current_task_id", return_value=None):
            assert StorageService.abort_operations(PAYLOAD, "disk-1") == ""
        storage.abort_operations.assert_not_called()
