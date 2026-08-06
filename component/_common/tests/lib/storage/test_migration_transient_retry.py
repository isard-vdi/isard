# SPDX-License-Identifier: AGPL-3.0-or-later

"""Transient-failure retry accounting for a recurring migration (#2343).

The existing recurring-drive tests cover the counter CLIMBING to quarantine
(occ 1 -> 2 -> 3 -> quarantined). What was never pinned is the case the ticket
names: a disk that FAILS transiently and then SUCCEEDS on a later occurrence.
Live, the only failure ever seen was permanent (missing source, fast-fail), so
`occurrence_failures` starting a fresh streak at 1 and a recovered disk NOT
being quarantined despite a prior failure had no coverage. These pin
`plan_tree_rearm`, the pure decision the runner drives at each occurrence edge.
"""

from isardvdi_common.lib.storage import migration as mig


def _item(state, occ, sid="r", tree="r"):
    return {
        "id": f"m--{sid}",
        "storage_id": sid,
        "tree_id": tree,
        "state": state,
        "occurrence_failures": occ,
    }


def test_first_transient_failure_starts_the_streak_at_one_and_rearms():
    """A disk failing for the FIRST time is re-armed to retry with the counter at
    1 — it must NOT quarantine (budget 3 not reached). This is the counter the
    ticket says had never run: a transient failure, watched."""
    ledger = [_item("failed", 0)]
    to_quarantine, to_rearm = mig.plan_tree_rearm(
        ledger, "retry_quarantine", quarantine_after=3
    )
    assert to_quarantine == []
    assert [(it["storage_id"], occ) for it, occ in to_rearm] == [("r", 1)]


def test_second_transient_failure_keeps_counting_below_budget():
    ledger = [_item("failed", 1)]
    to_quarantine, to_rearm = mig.plan_tree_rearm(
        ledger, "retry_quarantine", quarantine_after=3
    )
    assert to_quarantine == []
    assert [occ for _it, occ in to_rearm] == [2]


def test_disk_that_recovered_is_not_quarantined_despite_prior_failure():
    """The ticket's exact case: a disk that failed once (occurrence_failures=1)
    then SUCCEEDED (released) on the next attempt. At the following edge it is
    neither re-armed nor quarantined — recovery ended the streak; the counter
    only ever recorded the transient failure."""
    ledger = [_item("released", 1)]
    to_quarantine, to_rearm = mig.plan_tree_rearm(
        ledger, "retry_quarantine", quarantine_after=3
    )
    assert to_quarantine == []
    assert to_rearm == []


def test_mixed_tree_one_recovered_one_still_failing():
    """A recovered sibling does not save a still-failing one from its own count,
    and does not itself get re-armed."""
    ledger = [
        _item("released", 1, sid="r", tree="r"),
        _item("failed", 1, sid="c", tree="r"),
    ]
    to_quarantine, to_rearm = mig.plan_tree_rearm(
        ledger, "retry_quarantine", quarantine_after=3
    )
    assert to_quarantine == []
    # only the still-failing child is re-armed, its counter advanced to 2
    assert [(it["storage_id"], occ) for it, occ in to_rearm] == [("c", 2)]
