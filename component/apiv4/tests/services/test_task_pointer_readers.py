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


class TestAbortResolvesOnlyThroughTheIndex:
    """``abort_operations`` must read the live task ONCE, from the index.

    These exist because the four tests above cannot tell the correct
    implementation from the one the merge of this delivery can fabricate. When
    two branches both edit this function — one moving to the index, one still
    reading the retired ``storage.task`` — keeping "both sides" leaves a second
    ``tasks_from_ids`` call that silently overwrites the first. Measured: with
    that second read injected, every other abort test still passes.

    It cannot be caught by asserting on the outcome either, because the double
    is a ``MagicMock``: ``storage.task`` answers with a child mock, the loader
    is patched, and the function returns the same thing both ways. What
    separates them is *what was asked for*, so that is what these assert.
    """

    @patch("api.services.storage.get_storage")
    def test_the_retired_row_scalar_is_never_read(self, mock_get_storage):
        """One load, and with the id the index gave — not the row's field."""
        storage = MagicMock(id="disk-1")
        # A recognisable value: a bare MagicMock attribute would come back as a
        # child mock and a second read would be indistinguishable from the first.
        storage.task = "stale-pointer"
        mock_get_storage.return_value = storage
        with patch("api.services.storage.current_task_id", return_value="t-1"), patch(
            "api.services.storage.tasks_from_ids",
            return_value=[MagicMock(user_id="u-1")],
        ) as loader:
            StorageService.abort_operations(PAYLOAD, "disk-1")
        assert loader.call_count == 1, (
            "the live task was loaded %d times; a second load means something "
            "still reads the retired row pointer" % loader.call_count
        )
        assert list(loader.call_args_list[0].args[0]) == ["t-1"]

    @patch("api.services.storage.get_storage")
    def test_ownership_follows_the_index_not_the_stale_pointer(self, mock_get_storage):
        """The consequence, so the guard cannot silently invert.

        The index names a task somebody else started; the retired field still
        names one this caller owns. Reading the field lets the caller cancel
        work that is not theirs, and nothing about the response says so.

        ``TestAbortOperations`` above already checks the 403, but it cannot
        catch this: it patches the loader with a fixed ``return_value``, so both
        reads answer the same task and the verdict is identical either way. The
        two ids have to answer differently for the second read to be visible.
        """
        storage = MagicMock(id="disk-1")
        storage.task = "stale-pointer"
        mock_get_storage.return_value = storage
        owners = {"t-1": "someone-else", "stale-pointer": "u-1"}

        def load(ids, *args, **kwargs):
            return [MagicMock(user_id=owners[list(ids)[0]])]

        payload = {"user_id": "u-1", "category_id": "default", "role_id": "advanced"}
        with patch("api.services.storage.current_task_id", return_value="t-1"), patch(
            "api.services.storage.tasks_from_ids", side_effect=load
        ):
            with pytest.raises(Error) as raised:
                StorageService.abort_operations(payload, "disk-1")
        assert raised.value.status_code == 403
