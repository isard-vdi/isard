# SPDX-License-Identifier: AGPL-3.0-or-later

"""The admin listings carry the last task id, derived from the index.

Retiring the row pointer took ``task`` off these payloads, and the commit that
did it recorded that the desktop storage modal was its only consumer. It was
not: the webapp admin tables read the same field to label the Task column, to
gate Retry, to key the row a progress event is routed to, and for the media
"last task info" button. None of that is a yes/no question, so
``has_pending_task`` cannot serve it — they need the identifier, and the index
already holds it.

``last_task_id`` is deliberately NOT a liveness answer. It is the newest member
whose job still exists, so it may name a task that has already finished; that
is what "show the last task" and "retry it" mean. The busy question has its own
field. Keeping the two apart is the whole point: conflating them is the bug we
had to fix in ``has_pending_task``, and this is the more visible layer to
repeat it on.
"""

from unittest.mock import MagicMock, patch

from api.services.admin.media import AdminMediaService
from api.services.admin.storage import AdminStorageService

ADMIN = {"role_id": "admin", "category_id": "default", "user_id": "u-1"}


class TestStorageListing:
    def _run(self, rows, index):
        with patch(
            "api.services.admin.storage.StorageProcessed.get_storages",
            return_value=rows,
        ), patch("api.services.admin.storage.Task") as task_cls, patch(
            "api.services.admin.storage.last_task_ids", return_value=index
        ) as batched:
            task_cls._redis = MagicMock()
            return AdminStorageService.get_storages(ADMIN, status="ready"), batched

    def test_every_row_carries_its_last_task(self):
        rows = [{"id": "s-1"}, {"id": "s-2"}]
        out, _ = self._run(rows, {"s-1": "t-1", "s-2": None})
        assert [(r["id"], r["last_task_id"]) for r in out] == [
            ("s-1", "t-1"),
            ("s-2", None),
        ]

    def test_a_row_with_no_task_says_none_rather_than_missing_the_key(self):
        """The table binds a column to it; an absent key renders undefined."""
        out, _ = self._run([{"id": "s-1"}], {})
        assert "last_task_id" in out[0] and out[0]["last_task_id"] is None

    def test_the_index_is_read_once_for_the_whole_page(self):
        """A per-row lookup is two round trips per row; these tables render
        dozens, which is why the batched helper exists."""
        rows = [{"id": f"s-{n}"} for n in range(25)]
        _, batched = self._run(rows, {})
        assert batched.call_count == 1
        assert batched.call_args[0][1] == [f"s-{n}" for n in range(25)]


class TestMediaListing:
    def test_media_is_asked_under_its_own_namespace(self):
        """``media:`` and ``storage:`` are separate index keys; asking the wrong
        one answers None for every row, which is how the reconcile defect got in."""
        rows = [{"id": "m-1"}]
        with patch(
            "api.services.admin.media.MediaProcessed.admin_get_media",
            return_value=rows,
        ), patch("api.services.admin.media.Task") as task_cls, patch(
            "api.services.admin.media.last_task_ids", return_value={"m-1": "t-9"}
        ) as batched:
            task_cls._redis = MagicMock()
            out = AdminMediaService.get_media(ADMIN, status="Downloaded")
        assert out[0]["last_task_id"] == "t-9"
        assert batched.call_args.kwargs["kind"] == "media"
