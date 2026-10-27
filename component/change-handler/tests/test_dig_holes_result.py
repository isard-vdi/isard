# SPDX-License-Identifier: AGPL-3.0-or-later

"""A dig that does not finish is never lost: damaged on a mismatch, re-flagged
with its original since, re-checked after a partial punch, never retried where
the filesystem cannot punch."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _dig_result(status, exc_info, meta=None, since=None):
    from isardvdi_change_handler.task_results import storage

    task = SimpleNamespace(
        depending_status=status,
        dependencies=[
            SimpleNamespace(
                task="dig_holes",
                id="t1",
                exc_info=exc_info,
                job=SimpleNamespace(meta=meta or {}),
            )
        ],
    )
    row = MagicMock()
    setattr(row, "qemu-img-info", {"actual-size": 99})
    with patch.object(storage, "Storage") as cls:
        cls.exists.return_value = True
        cls.write_status.return_value = "damaged"
        cls.return_value = row
        storage.handle_dig_holes_result(task, "base", since=since)
    return cls


def _flags(cls):
    return [(c.args[1], c.kwargs.get("since")) for c in cls.flag_pending.call_args_list]


def test_a_dig_that_reads_back_differently_leaves_the_disk_damaged_for_review():
    from isardvdi_common.models.storage import DIG_HOLES_MISMATCH

    cls = _dig_result(
        "failed", f"RuntimeError: dig_holes: /x.qcow2 {DIG_HOLES_MISMATCH}"
    )
    cls.write_status.assert_called_once_with("base", "damaged")
    assert "damage_reason" in cls.update_document.call_args.args[1]
    cls.flag_pending.assert_called_once_with(
        "base", "review_damage", "dig_holes", {"task_id": "t1"}
    )


def test_a_finished_dig_marks_nothing():
    cls = _dig_result("finished", None)
    cls.write_status.assert_not_called()
    cls.flag_pending.assert_not_called()


@pytest.mark.parametrize("status", ["failed", "canceled"])
def test_a_dig_that_failed_before_punching_is_flagged_again_with_its_since(status):
    cls = _dig_result(status, "RuntimeError: no space left", since=1700)
    assert _flags(cls) == [("dig_holes", 1700)]
    cls.write_status.assert_not_called()


def test_a_dig_that_stopped_after_it_began_punching_is_checked_again():
    cls = _dig_result(
        "failed", "Work-horse terminated", meta={"dig_holes_punch": "started"}, since=5
    )
    assert _flags(cls) == [("check_integrity", None), ("dig_holes", 5)]


def test_a_filesystem_that_cannot_punch_is_recorded_and_never_retried():
    from isardvdi_common.lib.storage.zeros import DIG_HOLES_UNSUPPORTED

    cls = _dig_result(
        "failed",
        f"RuntimeError: dig_holes: /x.qcow2 {DIG_HOLES_UNSUPPORTED}",
        meta={"dig_holes_punch": "started"},
    )
    cls.flag_pending.assert_not_called()
    cls.clear_pending.assert_called_once_with("base", "dig_holes")
    cls.write_zeros.assert_called_once_with("base", 99, result="unsupported")


def test_the_worker_raises_the_markers_the_handler_reads():
    from pathlib import Path

    from isardvdi_common.models.storage import DIG_HOLES_MISMATCH

    worker = Path(__file__).parents[3] / "docker/storage/src/isardvdi_storage/task.py"
    source = worker.read_text()
    assert DIG_HOLES_MISMATCH in source
    assert "DIG_HOLES_UNSUPPORTED" in source and '"dig_holes_punch"' in source


def test_the_handler_is_registered_for_the_chain_step():
    from isardvdi_change_handler.task_results import registry, storage

    assert registry.HANDLERS["dig_holes_result"][0] is storage.handle_dig_holes_result
    assert "release_write_lock" not in registry.HANDLERS


def test_the_dig_hands_its_since_to_the_verdict():
    from isardvdi_common.models.storage import Storage

    storage = Storage.__new__(Storage)
    object.__setattr__(storage, "id", "s1")
    object.__setattr__(storage, "pending_actions", {"dig_holes": {"since": 42}})
    created = {}
    with (
        patch.object(Storage, "domains", new=[]),
        patch.object(Storage, "set_maintenance"),
        patch.object(Storage, "path", new="/p/s1.qcow2"),
        patch.object(Storage, "directory_path", new="/p", create=True),
        patch.object(Storage, "_maintenance_release_statuses", return_value={}),
        patch.object(Storage, "create_task", side_effect=lambda **k: created.update(k)),
        patch(
            "isardvdi_common.models.storage.StoragePool.get_best_for_action",
            return_value=SimpleNamespace(id="pool"),
        ),
    ):
        storage.dig_holes("u1")
    verdict = next(d for d in created["dependents"] if d["task"] == "dig_holes_result")
    assert verdict["job_kwargs"]["kwargs"] == {"storage_id": "s1", "since": 42}
