# SPDX-License-Identifier: AGPL-3.0-or-later

"""Progress counts what has actually MOVED, not only what has committed.

`done`/`bytes_done` count the committed tail only, so a tree with six disks
copied and none released read `0` and a few megabytes while hundreds of
gigabytes were on the destination. The copied figures are additive: the
committed ones keep their meaning.
"""

from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.models.storage_migration import (
    build_totals,
    compute_bytes_copied,
    compute_bytes_done,
    item_is_migrated,
)


def _items(*states, size=100):
    return [
        {
            "id": f"i{n}",
            "storage_id": f"s{n}",
            "tree_id": "s0",
            "state": st,
            "size_bytes": size,
            "kind": "desktop",
        }
        for n, st in enumerate(states)
    ]


def test_a_disk_on_the_destination_counts_before_it_commits():
    for state in ("moved", "rebased", "db_updated", "released"):
        assert item_is_migrated(state), state
    for state in ("pending", "preflight_ok", "moving", "failed", "skipped"):
        assert not item_is_migrated(state), state


def test_copied_bytes_lead_committed_bytes_mid_saga():
    items = _items("rebased", "rebased", "released", "moving", "pending")
    assert compute_bytes_copied(items) == 300
    assert compute_bytes_done(items) == 100


def test_totals_report_migrated_and_completed_apart_from_done():
    items = _items("rebased", "released", "skipped", "pending")
    totals = build_totals({}, items)
    # moved onto the destination: rebased + released
    assert totals["migrated"] == 2
    # committed, source freed: released only
    assert totals["completed"] == 1
    # needs no further saga work: released + skipped
    assert totals["done"] == 2
    assert totals["bytes_copied"] == 200
    assert totals["bytes_done"] == 100


def test_a_tree_with_everything_copied_and_nothing_released_is_not_zero():
    """The reading that made a live migration look stalled."""
    items = _items(*(["rebased"] * 6))

    class _M:
        id = "m1"
        status = "running"
        config = {}
        selection = {}
        current_window = None
        throughput_ewma = {}

    agg = mig.aggregate_status(_M(), items)
    tree = agg["trees"][0]
    assert tree["done"] == 0  # unchanged: nothing has committed yet
    assert tree["migrated"] == 6
    assert tree["bytes_copied"] == 600
    assert agg["totals"]["migrated"] == 6
    assert agg["totals"]["completed"] == 0
    assert agg["totals"]["bytes_copied"] == 600
