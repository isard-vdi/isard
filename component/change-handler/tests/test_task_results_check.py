# SPDX-License-Identifier: AGPL-3.0-or-later

"""A standalone integrity check records its verdict on the row: damaged on
corruption, a repair_leaks mark on leaks, last_checked_at either way, and
nothing at all when the check could not run."""

from types import SimpleNamespace
from unittest.mock import patch


def _run(depending_status, result, exists=True):
    from isardvdi_change_handler.task_results import storage

    task = SimpleNamespace(
        depending_status=depending_status,
        dependencies=[SimpleNamespace(task="storage_check", result=result)],
    )
    with patch.object(storage, "Storage") as cls:
        cls.exists.return_value = exists
        storage.handle_storage_check_result(task, storage_id="s1")
    return cls


def test_corruption_marks_the_row_damaged():
    cls = _run(
        "finished", {"ok": False, "summary": "corruptions=62", "corruptions": 62}
    )
    doc = cls.insert_document.call_args[0][0]
    assert doc["status"] == "damaged"
    assert doc["damage_reason"] == "corruptions=62"
    assert "last_checked_at" in doc
    cls.flag_pending.assert_not_called()


def test_leaks_flag_repair_leaks_and_the_disk_stays_ready():
    cls = _run("finished", {"ok": True, "summary": "leaks=593", "leaks": 593})
    cls.flag_pending.assert_called_once_with(
        "s1", "repair_leaks", "check_integrity", {"leaks": 593}
    )
    doc = cls.insert_document.call_args[0][0]
    assert "status" not in doc
    assert "last_checked_at" in doc


def test_a_clean_check_records_only_last_checked_at():
    cls = _run("finished", {"ok": True, "summary": "no errors", "leaks": 0})
    cls.flag_pending.assert_not_called()
    doc = cls.insert_document.call_args[0][0]
    assert set(doc) == {"id", "last_checked_at"}


def test_a_check_that_could_not_run_records_nothing():
    cls = _run("failed", None)
    cls.insert_document.assert_not_called()
    cls.flag_pending.assert_not_called()


def test_a_gone_row_records_nothing():
    cls = _run("finished", {"ok": True, "leaks": 0}, exists=False)
    cls.insert_document.assert_not_called()


def test_storage_check_result_is_registered():
    from isardvdi_change_handler.task_results import storage
    from isardvdi_change_handler.task_results.registry import HANDLERS

    handler, is_async = HANDLERS["storage_check_result"]
    assert handler is storage.handle_storage_check_result
    assert is_async is False
