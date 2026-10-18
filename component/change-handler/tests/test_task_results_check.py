# SPDX-License-Identifier: AGPL-3.0-or-later

"""A standalone integrity check records its verdict on the row through
``Storage.write_check``: damaged on corruption, a repair_leaks mark on leaks,
ready again for a damaged disk on a sound verdict. A check that reached no
verdict changes no status and leaves a check_inconclusive mark; a check whose
task failed records nothing."""

from types import SimpleNamespace
from unittest.mock import call, patch


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
        "finished",
        {
            "ok": False,
            "inconclusive": False,
            "summary": "corruptions=62",
            "corruptions": 62,
        },
    )
    cls.write_check.assert_called_once_with("s1", damage_reason="corruptions=62")
    cls.flag_pending.assert_not_called()
    cls.insert_document.assert_not_called()


def test_leaks_flag_repair_leaks_and_the_verdict_is_sound():
    cls = _run(
        "finished",
        {"ok": True, "inconclusive": False, "summary": "leaks=593", "leaks": 593},
    )
    cls.flag_pending.assert_called_once_with(
        "s1", "repair_leaks", "check_integrity", {"leaks": 593}
    )
    cls.write_check.assert_called_once_with("s1")
    cls.insert_document.assert_not_called()


def test_a_clean_check_writes_a_sound_verdict():
    cls = _run("finished", {"ok": True, "summary": "no errors", "leaks": 0})
    cls.flag_pending.assert_not_called()
    cls.write_check.assert_called_once_with("s1")
    cls.insert_document.assert_not_called()


def test_a_verdict_clears_the_inconclusive_mark():
    for result in (
        {"ok": True, "summary": "no errors", "leaks": 0},
        {"ok": False, "summary": "corruptions=1", "corruptions": 1},
    ):
        cls = _run("finished", result)
        assert cls.clear_pending.call_args_list == [call("s1", "check_inconclusive")]


def test_a_check_that_timed_out_is_inconclusive_not_damage():
    summary = "qemu-img check could not run: timed out after 120 seconds"
    cls = _run("finished", {"ok": False, "inconclusive": True, "summary": summary})
    cls.flag_pending.assert_called_once_with(
        "s1", "check_inconclusive", "check_integrity", {"summary": summary}
    )
    cls.write_check.assert_not_called()
    cls.clear_pending.assert_not_called()
    cls.insert_document.assert_not_called()
    cls.update_document.assert_not_called()


def test_a_check_that_could_not_open_the_image_is_inconclusive_not_damage():
    summary = "qemu-img: Could not open '/x.qcow2': Could not open backing file"
    cls = _run("finished", {"ok": False, "inconclusive": True, "summary": summary})
    cls.flag_pending.assert_called_once_with(
        "s1", "check_inconclusive", "check_integrity", {"summary": summary}
    )
    cls.write_check.assert_not_called()
    cls.insert_document.assert_not_called()


def test_a_check_whose_task_failed_records_nothing():
    cls = _run("failed", None)
    cls.write_check.assert_not_called()
    cls.insert_document.assert_not_called()
    cls.flag_pending.assert_not_called()


def test_a_gone_row_records_nothing():
    cls = _run("finished", {"ok": True, "leaks": 0}, exists=False)
    cls.write_check.assert_not_called()
    cls.insert_document.assert_not_called()


def test_storage_check_result_is_registered():
    from isardvdi_change_handler.task_results import storage
    from isardvdi_change_handler.task_results.registry import HANDLERS

    handler, is_async = HANDLERS["storage_check_result"]
    assert handler is storage.handle_storage_check_result
    assert is_async is False
