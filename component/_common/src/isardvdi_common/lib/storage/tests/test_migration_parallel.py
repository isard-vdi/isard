# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the P2.3 per-job parallelism DECISION layer (pure).

These pin how many independent trees may run at once: in-flight trees always
keep advancing, and the parallelism cap only gates the START of new trees so the
storage worker is never oversubscribed.
"""

from isardvdi_common.lib.storage import migration as mig


# --------------------------------------------------------------------------- #
# tree_phase
# --------------------------------------------------------------------------- #
def test_tree_phase_not_started():
    assert mig.tree_phase(["pending", "pending"]) == "not_started"


def test_tree_phase_in_flight():
    assert mig.tree_phase(["released", "moving"]) == "in_flight"
    assert mig.tree_phase(["db_updated", "pending"]) == "in_flight"


def test_tree_phase_done():
    assert mig.tree_phase(["released", "released"]) == "done"
    assert mig.tree_phase(["released", "skipped", "failed"]) == "done"
    assert mig.tree_phase([]) == "done"


# --------------------------------------------------------------------------- #
# admission_slots
# --------------------------------------------------------------------------- #
def test_slots_none_in_flight():
    # parallelism 2, nothing running -> 2 trees may start
    assert mig.admission_slots(["not_started", "not_started", "not_started"], 2) == 2


def test_slots_some_in_flight():
    # parallelism 2, one already in flight -> 1 slot left
    assert mig.admission_slots(["in_flight", "not_started", "not_started"], 2) == 1


def test_slots_saturated():
    # parallelism 2, two in flight -> no new trees
    assert mig.admission_slots(["in_flight", "in_flight", "not_started"], 2) == 0


def test_slots_done_trees_do_not_consume():
    # done trees are free; 1 in flight under cap 3 -> 2 slots
    assert mig.admission_slots(["done", "done", "in_flight", "not_started"], 3) == 2


def test_slots_parallelism_clamped_to_one():
    assert mig.admission_slots(["not_started", "not_started"], 0) == 1
    assert mig.admission_slots(["not_started", "not_started"], None) == 1
