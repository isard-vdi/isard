# SPDX-License-Identifier: AGPL-3.0-or-later

"""A dig whose file reads back differently leaves the disk damaged and for review."""

from types import SimpleNamespace
from unittest.mock import patch

import pytest


def _dig_result(status, exc_info):
    from isardvdi_change_handler.task_results import storage

    task = SimpleNamespace(
        depending_status=status,
        dependencies=[SimpleNamespace(task="dig_holes", id="t1", exc_info=exc_info)],
    )
    with (
        patch.object(storage.Storage, "exists", return_value=True),
        patch.object(
            storage.Storage, "write_status", return_value="damaged"
        ) as write_status,
        patch.object(storage.Storage, "update_document") as update,
        patch.object(storage.Storage, "flag_pending") as flag,
    ):
        storage.handle_dig_holes_result(task, "base")
    return write_status, update, flag


def test_a_dig_that_reads_back_differently_leaves_the_disk_damaged_for_review():
    from isardvdi_common.models.storage import DIG_HOLES_MISMATCH

    write_status, update, flag = _dig_result(
        "failed", f"RuntimeError: dig_holes: /x.qcow2 {DIG_HOLES_MISMATCH}"
    )
    write_status.assert_called_once_with("base", "damaged")
    assert "damage_reason" in update.call_args.args[1]
    flag.assert_called_once_with(
        "base", "review_damage", "dig_holes", {"task_id": "t1"}
    )


@pytest.mark.parametrize(
    "status, exc_info",
    [("failed", "RuntimeError: no space left"), ("finished", None)],
)
def test_any_other_outcome_marks_nothing(status, exc_info):
    write_status, update, flag = _dig_result(status, exc_info)
    write_status.assert_not_called()
    flag.assert_not_called()


def test_the_worker_raises_the_marker_the_handler_reads():
    from pathlib import Path

    from isardvdi_common.models.storage import DIG_HOLES_MISMATCH

    worker = Path(__file__).parents[3] / "docker/storage/src/isardvdi_storage/task.py"
    assert DIG_HOLES_MISMATCH in worker.read_text()


def test_the_handler_is_registered_for_the_chain_step():
    from isardvdi_change_handler.task_results import registry, storage

    assert registry.HANDLERS["dig_holes_result"][0] is storage.handle_dig_holes_result
    assert "release_write_lock" not in registry.HANDLERS
