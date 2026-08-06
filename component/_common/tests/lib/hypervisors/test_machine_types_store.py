#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``HypervisorsProcessed.update_hyper_machine_types`` must never blank a row.

The write is a whole-subdocument replace (``r.literal``) -- deliberately, since
a qemu upgrade REMOVES machine types and merging would keep advertising the
ones that just disappeared. The cost of that choice is that a report which
answers nothing must not reach it: ``discover_machine_types`` returns a
POPULATED dict whose ``machines`` is empty when libvirt could not be asked, and
writing that replaces a good 40-entry list with nothing. The engine reads an
empty list as "do not touch", so the correction would switch itself off on the
strength of one failed probe, silently, until the container restarts.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def store(monkeypatch):
    from isardvdi_common.lib.hypervisors import hypervisors as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        mod.HypervisorsProcessed, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.HypervisorsProcessed),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    table = MagicMock(name="table-hypervisors")
    monkeypatch.setattr(mod.r, "table", MagicMock(return_value=table))
    return mod.HypervisorsProcessed, table


def _wrote(table):
    return table.get.return_value.update.called


GOOD = {
    "machines": ["pc-i440fx-5.1", "pc-i440fx-10.0"],
    "aliases": {"pc": "pc-i440fx-10.0"},
    "reason": "ok",
}


def test_a_real_report_is_written(store):
    cls, table = store
    cls.update_hyper_machine_types("hyper-1", GOOD)
    assert _wrote(table)
    written = table.get.return_value.update.call_args[0][0]
    assert set(written) == {"machine_types"}


@pytest.mark.parametrize(
    "report",
    [
        {"machines": [], "aliases": {}, "reason": "libvirt_unreachable"},
        {"machines": [], "aliases": {}, "reason": "parse_error"},
        {
            "machines": [],
            "aliases": {"pc": "pc-i440fx-10.0"},
            "reason": "no_kvm_domain",
        },
        {"reason": "ok"},
    ],
)
def test_a_report_that_answers_nothing_is_refused(store, report):
    """Every one of these is a truthy dict -- testing the dict is the trap."""
    cls, table = store
    assert bool(report) is True
    cls.update_hyper_machine_types("hyper-1", report)
    assert not _wrote(table), "a failed probe must not replace the stored list"


@pytest.mark.parametrize("bad", [None, [], "pc-i440fx-5.1", 0])
def test_a_non_dict_is_refused(store, bad):
    cls, table = store
    cls.update_hyper_machine_types("hyper-1", bad)
    assert not _wrote(table)
