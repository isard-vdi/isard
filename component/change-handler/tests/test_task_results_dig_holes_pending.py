# SPDX-License-Identifier: AGPL-3.0-or-later

"""An exact zero scan flags dig_holes with its figure, clears a mark it no longer
supports, and drops a sparsify the zeros explain; a measurement leaves the marks alone."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from isardvdi_common.models.storage import DIG_HOLES_SLACK_BYTES, SPARSIFY_GROWTH_BYTES

SLACK = DIG_HOLES_SLACK_BYTES


def _domain(kind="desktop", status="Stopped"):
    return SimpleNamespace(id="d1", kind=kind, status=status)


def _row(
    marks=None, perms=("r", "w"), domains=None, children=(), size=7, status="ready"
):
    row = MagicMock(
        id="s1",
        perms=list(perms),
        status=status,
        pending_actions=marks,
        domains=[_domain()] if domains is None else domains,
    )
    row.get_children.return_value = list(children)
    setattr(row, "qemu-img-info", {"actual-size": size})
    return row


def _scan(reclaimable, row=None, depending="finished"):
    from isardvdi_change_handler.task_results import storage

    task = SimpleNamespace(
        depending_status=depending,
        dependencies=[
            SimpleNamespace(task="zero_scan", result={"reclaimable_bytes": reclaimable})
        ],
    )
    with patch.object(storage, "Storage") as cls:
        cls.exists.return_value = True
        cls.return_value = row or _row()
        storage.handle_zero_scan_result(task, "s1")
    return cls


def _flagged(cls):
    return [c.args[1] for c in cls.flag_pending.call_args_list]


def test_flags_dig_holes_with_the_exact_figure():
    cls = _scan(SLACK + 5)
    cls.flag_pending.assert_called_once_with(
        "s1", "dig_holes", found_by="zero scan", detail={"reclaimable_bytes": SLACK + 5}
    )


def test_records_the_scan_against_the_size_it_measured():
    cls = _scan(SLACK, _row(size=123))
    cls.write_zeros.assert_called_once_with("s1", 123, SLACK)


def test_flags_it_while_its_desktop_runs():
    cls = _scan(SLACK, _row(domains=[_domain(status="Started")]))
    assert _flagged(cls) == ["dig_holes"]


@pytest.mark.parametrize(
    "row",
    [
        _row(perms=("r",), domains=[_domain(kind="template")], children=[MagicMock()]),
        _row(domains=[]),
        _row(perms=("r",)),
        _row(children=[MagicMock(id="child")]),
    ],
    ids=["template-with-children", "unused", "read-only", "has-children"],
)
def test_a_disk_no_dig_may_write_is_not_flagged(row):
    assert "dig_holes" not in _flagged(_scan(10 * SLACK, row))


def test_flags_a_templates_disk_without_descendants():
    row = _row(perms=("r",), domains=[_domain(kind="template")])
    assert _flagged(_scan(SLACK, row)) == ["dig_holes"]


def test_clears_the_mark_once_the_zeros_are_gone():
    cls = _scan(0, _row(marks={"dig_holes": {"since": 1}}))
    cls.clear_pending.assert_called_once_with("s1", "dig_holes")
    cls.flag_pending.assert_not_called()


def test_leaves_an_unmarked_disk_alone():
    cls = _scan(SLACK - 1, _row(marks={"sparsify": {"since": 1}}))
    cls.clear_pending.assert_not_called()
    cls.flag_pending.assert_not_called()


@pytest.mark.parametrize("depending", ["failed", "canceled"])
def test_a_scan_that_did_not_finish_records_nothing(depending):
    cls = _scan(10 * SLACK, depending=depending)
    cls.write_zeros.assert_not_called()
    cls.flag_pending.assert_not_called()


def test_a_disk_no_longer_ready_is_recorded_but_not_marked():
    cls = _scan(10 * SLACK, _row(status="maintenance"))
    cls.write_zeros.assert_called_once()
    cls.flag_pending.assert_not_called()


def _sparsify(grew):
    return {"sparsify": {"since": 1, "detail": {"grew_bytes": grew}}}


def test_growth_that_is_only_zeros_drops_the_sparsify_mark():
    cls = _scan(4 * SLACK, _row(marks=_sparsify(4 * SLACK)))
    cls.clear_pending.assert_called_once_with("s1", "sparsify")


def test_growth_beyond_the_zeros_keeps_the_sparsify_mark():
    cls = _scan(SLACK, _row(marks=_sparsify(SLACK + SPARSIFY_GROWTH_BYTES)))
    assert ("s1", "sparsify") not in [c.args for c in cls.clear_pending.call_args_list]


def test_a_measurement_never_touches_the_dig_holes_mark():
    from isardvdi_change_handler.task_results import storage

    reading = {"id": "s1", "status": "ready", "qemu-img-info": {"actual-size": 1}}
    with patch.object(storage, "Storage") as cls:
        cls.exists.return_value = True
        cls.return_value = _row(marks={"dig_holes": {"since": 1}}, size=1)
        cls.write_reading.return_value = "ready"
        storage._apply_storage_update(reading)
    assert "dig_holes" not in _flagged(cls)
    cls.clear_pending.assert_not_called()


def test_the_handler_is_registered_for_the_chain_step():
    from isardvdi_change_handler.task_results import registry, storage

    assert registry.HANDLERS["zero_scan_result"][0] is storage.handle_zero_scan_result
