# SPDX-License-Identifier: AGPL-3.0-or-later

"""Usage-age threshold: move (and STOP) by how recently a tree was used.

The threshold is read against ``order`` and composes into one sentence:
``oldest_first`` moves only what has been idle for at least N days (stops at the
recently-used); ``newest_first`` moves only what was used within N days (stops at
the long-unused). A tree with no usage date is out of both directions unless the
admin includes it. These are the pure decisions; the plan wiring is exercised in
``test_migration.py`` and the runner re-scan in ``test_migration_rescan``.
"""

from isardvdi_common.lib.storage import migration as mig

NOW = 1_000_000  # fixed reference so the cutoff arithmetic is exact
DAY = 86400


def _key(days_ago):
    return NOW - days_ago * DAY


# --------------------------------------------------------------------------- #
# oldest_first — "move only what has NOT been used for at least N days"
# --------------------------------------------------------------------------- #
def test_oldest_first_moves_the_long_unused():
    # last used 30 days ago, threshold 7 -> older than the cutoff -> moves
    assert mig.tree_within_age_threshold(_key(30), "oldest_first", NOW, 7) is True


def test_oldest_first_stops_at_the_recently_used():
    # last used 2 days ago, threshold 7 -> within the window -> stays
    assert mig.tree_within_age_threshold(_key(2), "oldest_first", NOW, 7) is False


def test_oldest_first_boundary_is_strict():
    # exactly at the cutoff (used N days ago) is NOT "at least N days idle"
    assert mig.tree_within_age_threshold(_key(7), "oldest_first", NOW, 7) is False


# --------------------------------------------------------------------------- #
# newest_first — "move only what HAS been used within the last N days"
# --------------------------------------------------------------------------- #
def test_newest_first_moves_the_recently_used():
    assert mig.tree_within_age_threshold(_key(2), "newest_first", NOW, 7) is True


def test_newest_first_stops_at_the_long_unused():
    assert mig.tree_within_age_threshold(_key(30), "newest_first", NOW, 7) is False


def test_newest_first_boundary_is_inclusive():
    # exactly N days ago counts as "used within N days" -> the two directions are
    # exact inverses at the boundary, so a disk is never in neither/both.
    assert mig.tree_within_age_threshold(_key(7), "newest_first", NOW, 7) is True


def test_directions_are_exact_inverses_off_the_boundary():
    for days in (0, 1, 6, 8, 30, 365):
        old = mig.tree_within_age_threshold(_key(days), "oldest_first", NOW, 7)
        new = mig.tree_within_age_threshold(_key(days), "newest_first", NOW, 7)
        assert old != new


# --------------------------------------------------------------------------- #
# no usage date — excluded on BOTH sides unless opted in
# --------------------------------------------------------------------------- #
def test_never_used_excluded_by_default_both_directions():
    assert mig.tree_within_age_threshold(None, "oldest_first", NOW, 7) is False
    assert mig.tree_within_age_threshold(None, "newest_first", NOW, 7) is False


def test_never_used_included_when_opted_in():
    assert (
        mig.tree_within_age_threshold(
            None, "oldest_first", NOW, 7, include_never_used=True
        )
        is True
    )
    assert (
        mig.tree_within_age_threshold(
            None, "newest_first", NOW, 7, include_never_used=True
        )
        is True
    )


# --------------------------------------------------------------------------- #
# no direction / no threshold — admit everything (the API rejects order=none
# WITH a threshold up front; this is the pure-layer defence)
# --------------------------------------------------------------------------- #
def test_order_none_never_filters():
    assert mig.tree_within_age_threshold(_key(2), "none", NOW, 7) is True
    assert mig.tree_within_age_threshold(None, "none", NOW, 7) is True


def test_no_threshold_admits_everything():
    assert mig.tree_within_age_threshold(_key(999), "oldest_first", NOW, None) is True
    assert mig.tree_within_age_threshold(_key(0), "oldest_first", NOW, 0) is True


# --------------------------------------------------------------------------- #
# summarize_plan carries the exclusion counts so the preview can show "M outside"
# --------------------------------------------------------------------------- #
def test_summarize_plan_reports_usage_age_exclusions():
    items = [
        {"tree_id": "a", "storage_id": "a", "kind": "desktop", "size_bytes": 100},
    ]
    age_excluded = [
        {"tree_id": "b", "order_key": _key(1), "disks": 2, "bytes": 500},
        {"tree_id": "c", "order_key": _key(0), "disks": 1, "bytes": 300},
    ]
    totals = mig.summarize_plan(items, age_excluded=age_excluded, usage_age_days=7)
    assert totals["usage_age_days"] == 7
    assert totals["usage_age_excluded_trees"] == 2
    assert totals["usage_age_excluded_disks"] == 3
    assert totals["usage_age_excluded_bytes"] == 800
    # the ordinary totals are what falls WITHIN the threshold
    assert totals["trees"] == 1
    assert totals["bytes_total"] == 100


def test_summarize_plan_usage_age_absent_by_default():
    totals = mig.summarize_plan([])
    assert totals["usage_age_days"] is None
    assert totals["usage_age_excluded_trees"] == 0
