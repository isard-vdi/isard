# SPDX-License-Identifier: AGPL-3.0-or-later

"""Sparsify pending-action, flag side.

A ready, writable disk whose measured actual-size grew by at least
``SPARSIFY_GROWTH_BYTES`` since its last measurement is flagged for sparsify
when a storage_update writes the fresh qemu-img-info. A template, a first
measurement, a sub-threshold growth, a shrink, a non-ready row, or an update
that carries no measurement is not flagged.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from isardvdi_common.models.storage import SPARSIFY_GROWTH_BYTES

THRESHOLD = SPARSIFY_GROWTH_BYTES


def _old_row(actual_size, perms=("r", "w"), status="ready"):
    row = MagicMock()
    row.perms = list(perms)
    row.status = status
    setattr(
        row,
        "qemu-img-info",
        None if actual_size is None else {"actual-size": actual_size},
    )
    return row


def _apply(storage_dict, old_row):
    from isardvdi_change_handler.task_results import storage

    with patch.object(storage, "Storage") as cls:
        cls.exists.return_value = True
        cls.return_value = old_row
        cls.init_document.return_value = MagicMock(domains=[])
        storage._apply_storage_update(storage_dict)
    return cls


def test_flags_sparsify_when_disk_grew_over_threshold():
    cls = _apply(
        {
            "id": "s1",
            "status": "ready",
            "qemu-img-info": {"actual-size": 1_000_000_000 + THRESHOLD},
        },
        _old_row(1_000_000_000),
    )
    cls.flag_pending.assert_called_once_with(
        "s1", "sparsify", found_by="storage refresh", detail={"grew_bytes": THRESHOLD}
    )


def test_does_not_flag_when_growth_below_threshold():
    cls = _apply(
        {
            "id": "s1",
            "status": "ready",
            "qemu-img-info": {"actual-size": 1_000_000_000 + THRESHOLD - 1},
        },
        _old_row(1_000_000_000),
    )
    cls.flag_pending.assert_not_called()


def test_does_not_flag_on_first_measurement():
    cls = _apply(
        {
            "id": "s1",
            "status": "ready",
            "qemu-img-info": {"actual-size": 10 * THRESHOLD},
        },
        _old_row(None),
    )
    cls.flag_pending.assert_not_called()


def test_does_not_flag_a_readonly_template_disk():
    cls = _apply(
        {
            "id": "s1",
            "status": "ready",
            "qemu-img-info": {"actual-size": 1_000_000_000 + 10 * THRESHOLD},
        },
        _old_row(1_000_000_000, perms=("r",)),
    )
    cls.flag_pending.assert_not_called()


def test_does_not_flag_when_row_is_not_ready():
    cls = _apply(
        {"id": "s1", "qemu-img-info": {"actual-size": 1_000_000_000 + 10 * THRESHOLD}},
        _old_row(1_000_000_000, status="maintenance"),
    )
    cls.flag_pending.assert_not_called()


def test_does_not_flag_without_a_fresh_measurement():
    cls = _apply({"id": "s1", "status": "ready"}, _old_row(1_000_000_000))
    cls.flag_pending.assert_not_called()


def test_does_not_flag_when_disk_shrank():
    cls = _apply(
        {
            "id": "s1",
            "status": "ready",
            "qemu-img-info": {"actual-size": 1_000_000_000},
        },
        _old_row(5_000_000_000),
    )
    cls.flag_pending.assert_not_called()


# ---------------------------------------------------------------------------
# clear side: handle_clear_pending_action (the sparsify chain's finalize step)
# ---------------------------------------------------------------------------


def _clear(depending_status, exists=True):
    from isardvdi_change_handler.task_results import storage

    task = SimpleNamespace(depending_status=depending_status)
    with patch.object(storage, "Storage") as cls:
        cls.exists.return_value = exists
        storage.handle_clear_pending_action(task, storage_id="s1", action="sparsify")
    return cls


def test_clears_pending_action_when_chain_finished():
    cls = _clear("finished")
    cls.clear_pending.assert_called_once_with("s1", "sparsify")


def test_does_not_clear_when_chain_did_not_finish():
    cls = _clear("failed")
    cls.clear_pending.assert_not_called()


def test_does_not_clear_when_row_is_gone():
    cls = _clear("finished", exists=False)
    cls.clear_pending.assert_not_called()


def test_clear_pending_action_is_registered():
    from isardvdi_change_handler.task_results import storage
    from isardvdi_change_handler.task_results.registry import HANDLERS

    handler, is_async = HANDLERS["clear_pending_action"]
    assert handler is storage.handle_clear_pending_action
    assert is_async is False
