# SPDX-License-Identifier: AGPL-3.0-or-later

"""The cheaper action goes first, the budget counts what is read, and a pass examines a bounded number of rows."""

from isardvdi_common.lib.storage.actions import DISK_ACTIONS
from isardvdi_common.lib.storage.sweep import (
    bytes_read,
    examine_cap,
    superseding_marks,
    sweep_order,
)


def test_dig_holes_runs_before_the_sparsify_it_supersedes():
    order = sweep_order()
    assert order.index("dig_holes") < order.index("sparsify")


def test_the_preference_lives_in_the_action_registry():
    assert "sparsify" in DISK_ACTIONS["dig_holes"].supersedes


def test_sparsify_yields_to_an_enabled_dig_holes_only():
    assert superseding_marks("sparsify", ["dig_holes", "sparsify"]) == {"dig_holes"}
    assert superseding_marks("sparsify", ["sparsify"]) == set()
    assert superseding_marks("dig_holes", ["dig_holes", "sparsify"]) == set()


def test_a_verified_dig_reads_the_file_three_times():
    assert bytes_read("dig_holes", 10) == 30
    assert bytes_read("zero_scan", 10) == 10
    assert bytes_read("sparsify", None) == 0


def test_the_rows_examined_are_capped():
    assert examine_cap(50) == 500
    assert examine_cap(None) == examine_cap(0) == 10_000
