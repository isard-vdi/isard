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

from isardvdi_common.models.storage import (
    SPARSIFY_GROWTH_BYTES,
    SPARSIFY_GROWTH_MAX_BASELINE_AGE_S,
)

THRESHOLD = SPARSIFY_GROWTH_BYTES
_NOW = 1_000_000_000
_RECENT = _NOW - 60  # baseline read a minute ago
_STALE = _NOW - SPARSIFY_GROWTH_MAX_BASELINE_AGE_S - 1  # just past the window


def _old_row(
    actual_size, perms=("r", "w"), status="ready", info_at=_RECENT, marks=None
):
    row = MagicMock()
    row.perms = list(perms)
    row.status = status
    row.qemu_img_info_at = info_at
    row.pending_actions = marks
    setattr(
        row,
        "qemu-img-info",
        None if actual_size is None else {"actual-size": actual_size},
    )
    return row


def _growth_mark(grew=THRESHOLD, found_by="storage refresh"):
    return {
        "sparsify": {"since": 1, "found_by": found_by, "detail": {"grew_bytes": grew}}
    }


def _apply(storage_dict, old_row, accepted=True):
    from isardvdi_change_handler.task_results import storage

    with patch.object(storage, "Storage") as cls, patch.object(
        storage, "time", return_value=_NOW
    ):
        cls.exists.return_value = True
        cls.return_value = old_row
        cls.write_reading.return_value = (
            storage_dict.get("status") or "ready" if accepted else None
        )
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


def test_does_not_flag_a_reading_the_row_refused():
    """A stale reading is not written, so it says nothing about growth."""
    cls = _apply(
        {
            "id": "s1",
            "status": "ready",
            "qemu-img-info": {"actual-size": 1_000_000_000 + 10 * THRESHOLD},
        },
        _old_row(1_000_000_000),
        accepted=False,
    )
    cls.flag_pending.assert_not_called()


def test_does_not_flag_growth_over_a_stale_baseline():
    """Growth measured against a reading older than the window is not a sparsify
    signal: over so long it may be organic data, not reclaimable churn."""
    cls = _apply(
        {
            "id": "s1",
            "status": "ready",
            "qemu-img-info": {"actual-size": 1_000_000_000 + 10 * THRESHOLD},
        },
        _old_row(1_000_000_000, info_at=_STALE),
    )
    cls.flag_pending.assert_not_called()


def test_does_not_flag_growth_when_the_baseline_has_no_timestamp():
    """A legacy row with no recorded measurement time: its age is unknown, so the
    growth is not trusted (flagging resumes once the row is re-measured)."""
    cls = _apply(
        {
            "id": "s1",
            "status": "ready",
            "qemu-img-info": {"actual-size": 1_000_000_000 + 10 * THRESHOLD},
        },
        _old_row(1_000_000_000, info_at=None),
    )
    cls.flag_pending.assert_not_called()


def test_a_reading_that_no_longer_grows_retracts_a_stale_growth_mark():
    """A6 stopped setting a growth mark over a stale baseline; one an older reading
    already left behind is retracted on the next reading that no longer grows, so
    the false marks clear themselves without a migration."""
    cls = _apply(
        {
            "id": "s1",
            "status": "ready",
            "qemu-img-info": {"actual-size": 1_000_000_000},
        },
        _old_row(1_000_000_000, marks=_growth_mark()),
    )
    cls.flag_pending.assert_not_called()
    cls.clear_pending.assert_called_once_with("s1", "sparsify")


def test_a_sparsify_mark_from_elsewhere_is_not_retracted():
    """Only the growth heuristic's own marks self-heal; one from another source
    (e.g. an admin) is left for its own chain to clear."""
    cls = _apply(
        {
            "id": "s1",
            "status": "ready",
            "qemu-img-info": {"actual-size": 1_000_000_000},
        },
        _old_row(1_000_000_000, marks={"sparsify": {"since": 1, "found_by": "admin"}}),
    )
    assert ("s1", "sparsify") not in [c.args for c in cls.clear_pending.call_args_list]


def test_a_reading_that_grows_flags_and_never_retracts():
    cls = _apply(
        {
            "id": "s1",
            "status": "ready",
            "qemu-img-info": {"actual-size": 1_000_000_000 + THRESHOLD},
        },
        _old_row(1_000_000_000, marks=_growth_mark()),
    )
    cls.flag_pending.assert_called_once_with(
        "s1", "sparsify", found_by="storage refresh", detail={"grew_bytes": THRESHOLD}
    )
    assert ("s1", "sparsify") not in [c.args for c in cls.clear_pending.call_args_list]


def test_flags_growth_over_a_fresh_baseline():
    """The flip side: the same growth over a recent baseline still flags."""
    cls = _apply(
        {
            "id": "s1",
            "status": "ready",
            "qemu-img-info": {"actual-size": 1_000_000_000 + THRESHOLD},
        },
        _old_row(1_000_000_000, info_at=_RECENT),
    )
    cls.flag_pending.assert_called_once_with(
        "s1", "sparsify", found_by="storage refresh", detail={"grew_bytes": THRESHOLD}
    )


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
