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


def test_item_state_is_not_a_budget_basis():
    """Regression guard. The first implementation summed size_bytes over item
    STATES, which is cumulative for the job's life and wedged every recurring
    job with a budget after its first occurrence. The accounting must come from
    the audit records, so a bare state carries no bytes at all."""
    state_only = [
        {"state": "released", "size_bytes": 100},
        {"state": "moved", "size_bytes": 50},
    ]
    assert mig.occurrence_bytes_moved(state_only, "initial") == 0


def test_budget_of_zero_means_unlimited():
    assert mig.budget_allows_new_tree(10**12, 0) is True


def test_budget_allows_a_new_tree_below_the_cap():
    assert mig.budget_allows_new_tree(999, 1000) is True


def test_budget_stops_new_trees_once_reached():
    assert mig.budget_allows_new_tree(1000, 1000) is False
    assert mig.budget_allows_new_tree(1001, 1000) is False


# --------------------------------------------------------------------------- #
# The budget must be PER OCCURRENCE. Item state is not a usable basis: a
# released item keeps that state for the job's whole life and re-arm never
# resets it, so a state-based sum spends a recurring job's budget once and for
# ever. The append-only audit records carry the occurrence they belong to.
# --------------------------------------------------------------------------- #
def _audited(occurrence, size, result="moved_ok"):
    return {
        "state": "released",
        "size_bytes": size,
        "audit": [{"occurrence": occurrence, "size_bytes": size, "result": result}],
    }


def test_bytes_moved_counts_only_the_current_occurrence():
    items = [
        _audited("night-1", 100),
        _audited("night-1", 50),
        _audited("night-2", 7),
    ]
    assert mig.occurrence_bytes_moved(items, "night-2") == 7
    assert mig.occurrence_bytes_moved(items, "night-1") == 150


def test_a_recurring_job_does_not_inherit_the_previous_occurrence_budget():
    """The wedge this prevents: night 1 spends the whole budget, night 2 starts
    with a clean one instead of being blocked for the rest of the job's life."""
    spent_night_1 = [_audited("night-1", 500)]
    assert (
        mig.budget_allows_new_tree(
            mig.occurrence_bytes_moved(spent_night_1, "night-1"), 500
        )
        is False
    )
    # same ledger, next occurrence -> the budget is available again
    assert (
        mig.budget_allows_new_tree(
            mig.occurrence_bytes_moved(spent_night_1, "night-2"), 500
        )
        is True
    )


def test_an_in_place_disk_does_not_spend_budget():
    """``in_place`` means nothing was copied, so it must not consume a volume
    budget even though the item is released and audited."""
    items = [_audited("initial", 900, result="in_place")]
    assert mig.occurrence_bytes_moved(items, "initial") == 0


def test_a_one_shot_job_uses_the_initial_occurrence():
    items = [_audited("initial", 42)]
    assert mig.occurrence_bytes_moved(items, "initial") == 42
