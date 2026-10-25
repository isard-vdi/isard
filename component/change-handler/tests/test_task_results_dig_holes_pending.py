# SPDX-License-Identifier: AGPL-3.0-or-later

"""A measurement that finds zeros a dig could give back flags dig_holes; one that does not clears it."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from isardvdi_common.models.storage import DIG_HOLES_SLACK_BYTES

SLACK = DIG_HOLES_SLACK_BYTES


def _domain(kind="desktop", status="Stopped"):
    return SimpleNamespace(id="d1", kind=kind, status=status)


def _row(marks=None, perms=("r", "w"), domains=None, children=(), old_size=1):
    row = MagicMock(
        id="s1",
        perms=list(perms),
        status="ready",
        pending_actions=marks,
        domains=[_domain()] if domains is None else domains,
    )
    row.get_children.return_value = list(children)
    setattr(row, "qemu-img-info", {"actual-size": old_size})
    return row


def _apply(storage_dict, row=None, accepted=True):
    from isardvdi_change_handler.task_results import storage

    with patch.object(storage, "Storage") as cls:
        cls.exists.return_value = True
        cls.return_value = row or _row()
        cls.write_reading.return_value = (
            storage_dict.get("status", "ready") if accepted else None
        )
        storage._apply_storage_update(storage_dict)
    return cls


def _reading(reclaimable, status="ready", actual_size=1):
    return {
        "id": "s1",
        "status": status,
        "qemu-img-info": {"actual-size": actual_size},
        "reclaimable-zeros": reclaimable,
    }


def _flagged(cls):
    return [c.args[1] for c in cls.flag_pending.call_args_list]


def test_flags_a_desktop_disk_that_allocates_enough_zeros():
    cls = _apply(_reading(SLACK))
    cls.flag_pending.assert_called_once_with(
        "s1",
        "dig_holes",
        found_by="storage refresh",
        detail={"reclaimable_bytes": SLACK},
    )


def test_flags_it_while_its_desktop_runs():
    cls = _apply(_reading(SLACK), _row(domains=[_domain(status="Started")]))
    assert _flagged(cls) == ["dig_holes"]


def test_the_figure_is_never_written_to_the_row():
    cls = _apply(_reading(SLACK))
    assert "reclaimable-zeros" not in cls.write_reading.call_args.args[0]


@pytest.mark.parametrize(
    "row",
    [
        _row(domains=[_domain(kind="template")]),
        _row(domains=[]),
        _row(perms=("r",)),
        _row(children=[MagicMock(id="child")]),
    ],
    ids=["template", "unused", "read-only", "has-children"],
)
def test_a_disk_no_dig_may_write_is_not_flagged(row):
    cls = _apply(_reading(10 * SLACK), row)
    assert "dig_holes" not in _flagged(cls)


def test_a_mark_the_disk_no_longer_qualifies_for_is_cleared():
    row = _row(marks={"dig_holes": {"since": 1}}, domains=[_domain(kind="template")])
    cls = _apply(_reading(10 * SLACK), row)
    cls.clear_pending.assert_called_once_with("s1", "dig_holes")


def test_clears_the_mark_once_the_zeros_are_gone():
    cls = _apply(_reading(0), _row(marks={"dig_holes": {"since": 1}}))
    cls.clear_pending.assert_called_once_with("s1", "dig_holes")
    cls.flag_pending.assert_not_called()


def test_leaves_an_unmarked_disk_alone():
    cls = _apply(_reading(SLACK - 1), _row(marks={"sparsify": {"since": 1}}))
    cls.clear_pending.assert_not_called()
    cls.flag_pending.assert_not_called()


def test_a_refused_reading_marks_nothing():
    cls = _apply(_reading(10 * SLACK), accepted=False)
    cls.flag_pending.assert_not_called()


def test_a_disk_that_is_not_ready_is_not_marked():
    cls = _apply(_reading(10 * SLACK, status="maintenance"))
    cls.flag_pending.assert_not_called()


def test_a_reading_without_the_figure_says_nothing():
    reading = _reading(0)
    del reading["reclaimable-zeros"]
    cls = _apply(reading, _row(marks={"dig_holes": {"since": 1}}))
    cls.clear_pending.assert_not_called()
    cls.flag_pending.assert_not_called()


def test_growth_that_is_only_zeros_is_not_a_sparsify_mark():
    cls = _apply(_reading(SLACK * 4, actual_size=1 + SLACK * 4))
    assert _flagged(cls) == ["dig_holes"]


def test_growth_beyond_the_zeros_is_still_a_sparsify_mark():
    cls = _apply(_reading(SLACK, actual_size=1 + SLACK * 4))
    assert sorted(_flagged(cls)) == ["dig_holes", "sparsify"]
