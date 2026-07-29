# SPDX-License-Identifier: AGPL-3.0-or-later

"""Per-occurrence volume budget.

The operator, not a probe, decides how much a night may move. This matters most
where a probe cannot help: on a thin-provisioned pool (VDO) the filesystem
reports LOGICAL free space while the real constraint is physical fill, so a
statvfs floor gives false safety. A byte budget needs no filesystem
introspection at all, so it is correct there too.

The budget bounds only the STARTING of new trees: a tree already in flight
always finishes, because stopping mid-tree would leave a half-migrated chain.
"""

from isardvdi_common.lib.storage import migration as mig


def _it(state, size):
    return {"state": state, "size_bytes": size}


def test_bytes_moved_counts_only_disks_that_actually_landed():
    items = [
        _it("released", 100),
        _it("db_updated", 50),
        _it("moved", 25),
        _it("moving", 999),  # in flight, not landed
        _it("pending", 999),  # never started
        _it("skipped", 999),  # never moved
    ]
    assert mig.occurrence_bytes_moved(items) == 175


def test_budget_of_zero_means_unlimited():
    assert mig.budget_allows_new_tree(10**12, 0) is True


def test_budget_allows_a_new_tree_below_the_cap():
    assert mig.budget_allows_new_tree(999, 1000) is True


def test_budget_stops_new_trees_once_reached():
    assert mig.budget_allows_new_tree(1000, 1000) is False
    assert mig.budget_allows_new_tree(1001, 1000) is False
