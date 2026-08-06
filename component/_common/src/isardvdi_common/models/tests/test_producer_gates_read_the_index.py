# SPDX-License-Identifier: AGPL-3.0-or-later

"""The "row already busy" gates resolve through the task index, not the row.

The scalar ``task`` field can only name one chain and is never cleared, so it
answers "busy" for a row whose job expired months ago and cannot answer at all
for a row locked by a chain it did not create. The index answers both, and
``current_task_id`` is the single primitive: the newest member whose job still
exists, or nothing.

That last part matters for the gate specifically: reading the scalar, a row
whose pointer outlived its job was refused work forever until something
happened to overwrite the field. Reading the index, the row is free the moment
its work is really gone.
"""

from unittest.mock import MagicMock, patch

import pytest
from isardvdi_common.models.storage import Storage


def _disk(**extra):
    disk = Storage.__new__(Storage)
    disk.__dict__.update({"id": "disk-1", "task": None, **extra})
    return disk


def _run_create_task(disk, current, pending=True):
    """Run the real ``create_task`` gate with the index answering ``current``."""
    with patch(
        "isardvdi_common.models.storage.current_task_id", return_value=current
    ) as current_task, patch("isardvdi_common.models.storage.Task") as Task, patch(
        "isardvdi_common.models.storage.queue_coverage.enforce_shed"
    ), patch.object(
        Storage, "category", "cat-1"
    ), patch.object(
        Storage, "__setattr__", lambda self, name, value: None
    ):
        Task.exists.return_value = True
        Task.return_value.pending = pending
        Task._redis = MagicMock()
        built = MagicMock()
        built.id = "new-task"
        Task.side_effect = None
        Task.return_value.id = "new-task"
        disk.create_task(user_id="u-1", queue="storage.pool.default", task="convert")
    return current_task


class TestTheBusyGate:
    def test_a_row_with_a_live_task_is_refused(self):
        with pytest.raises(Exception) as excinfo:
            _run_create_task(_disk(), current="task-1", pending=True)
        assert getattr(excinfo.value, "status_code", None) == 428
        assert "task-1" in str(excinfo.value)

    def test_a_row_the_index_calls_free_is_admitted(self):
        """Including the case the scalar could never express: a pointer whose
        job is gone. The index simply has no live member, so the row is free."""
        _run_create_task(_disk(task="expired-months-ago"), current=None)

    def test_a_settled_task_does_not_block(self):
        _run_create_task(_disk(), current="task-1", pending=False)

    def test_the_gate_asks_the_index_about_this_row(self):
        current_task = _run_create_task(_disk(), current=None)
        assert current_task.call_args.args[1] == "disk-1"

    def test_the_row_scalar_is_not_consulted(self):
        """A row still carrying a stale pointer must not be refused work for
        it: the field is retired, and until it is deleted it must not be read
        either, or the two sources disagree again."""
        _run_create_task(_disk(task="stale-pointer"), current=None)
