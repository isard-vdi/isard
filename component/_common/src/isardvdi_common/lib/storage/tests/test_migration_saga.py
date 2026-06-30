# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the per-disk migration saga DECISION layer (pure).

These pin the correctness-critical ordering invariants:
  * top-to-bottom, strictly serial within a tree (one disk in flight),
  * a child only starts once its parent has been moved+rebased+committed
    (``db_updated``) so the child's rebase target exists,
  * the root never rebases,
  * source deletion (release) happens only AFTER the whole tree is committed
    (move_delete fires last — never a parent-delete-before-child-rebase race),
  * a failed disk blocks its tree.
The executor that performs the real RQ/DB ops is exercised live (P1 gate).
"""

from isardvdi_common.lib.storage import migration as mig


def _item(topo, state, **kw):
    base = {
        "storage_id": f"s{topo}",
        "tree_id": "s0",
        "topo_index": topo,
        "state": state,
        "parent_dst_path": None if topo == 0 else "/new/parent.qcow2",
    }
    base.update(kw)
    return base


def _status(mapping):
    return lambda tid: mapping.get(tid)


# --------------------------------------------------------------------------- #
# decide_item_action — per-state transitions
# --------------------------------------------------------------------------- #
def test_pending_starts_move():
    assert mig.decide_item_action(_item(0, "pending"), _status({})) == "start_move"


def test_moving_waits_until_move_finishes():
    it = _item(0, "moving", move_task_id="m1")
    assert mig.decide_item_action(it, _status({"m1": "started"})) == "wait"
    assert mig.decide_item_action(it, _status({"m1": "finished"})) == "mark_moved"
    assert mig.decide_item_action(it, _status({"m1": "failed"})) == "fail"


def test_root_skips_rebase():
    it = _item(0, "moved", move_task_id="m1")  # topo 0 => root
    assert mig.decide_item_action(it, _status({})) == "skip_rebase"


def test_nonroot_starts_then_awaits_rebase():
    it = _item(1, "moved", move_task_id="m1")
    # no rebase task yet -> start it
    assert mig.decide_item_action(it, _status({})) == "start_rebase"
    it2 = _item(1, "moved", move_task_id="m1", rebase_task_id="r1")
    assert mig.decide_item_action(it2, _status({"r1": "started"})) == "wait"
    assert mig.decide_item_action(it2, _status({"r1": "finished"})) == "mark_rebased"
    assert mig.decide_item_action(it2, _status({"r1": "failed"})) == "fail"


def test_rebased_triggers_db_update():
    it = _item(1, "rebased")
    assert mig.decide_item_action(it, _status({})) == "db_update"


# --------------------------------------------------------------------------- #
# resume: a LOST in-flight task (redis expired/cleared) is re-enqueued.
# move (remove_source_file=False) and rebase -u are both idempotent, so
# re-running a step that may have already completed is safe.
# --------------------------------------------------------------------------- #
def test_moving_with_lost_job_reenqueues_move():
    it = _item(0, "moving", move_task_id="gone")
    # status None == the RQ job no longer exists (lost on a restart)
    assert mig.decide_item_action(it, _status({})) == "start_move"


def test_moved_with_lost_rebase_job_reenqueues_rebase():
    it = _item(1, "moved", move_task_id="m1", rebase_task_id="gone")
    assert mig.decide_item_action(it, _status({})) == "start_rebase"


# --------------------------------------------------------------------------- #
# tick_made_progress — lets the scheduler drain loop stop when every tree is
# only waiting on an in-flight task (instead of spinning).
# --------------------------------------------------------------------------- #
def test_tick_made_progress_true_when_a_tree_advanced():
    assert mig.tick_made_progress([("r1", "i1", "start_move")]) is True
    assert (
        mig.tick_made_progress([("r1", "i1", "wait"), ("r2", "i2", "db_update")])
        is True
    )


def test_tick_made_progress_false_when_all_waiting_or_terminal():
    assert mig.tick_made_progress([("r1", "i1", "wait")]) is False
    assert (
        mig.tick_made_progress(
            [("r1", None, "done"), ("r2", "i2", "gated"), ("r3", "i3", "blocked")]
        )
        is False
    )
    assert mig.tick_made_progress([]) is False


# --------------------------------------------------------------------------- #
# tree_next — ordering across a tree
# --------------------------------------------------------------------------- #
def test_tree_serial_top_to_bottom():
    # root still pending -> work the root, not the child
    items = [_item(0, "pending"), _item(1, "pending")]
    item, action = mig.tree_next(items, _status({}))
    assert item["topo_index"] == 0 and action == "start_move"


def test_tree_child_starts_only_after_parent_committed():
    # root db_updated (moved+rebased+committed) -> child may now start
    items = [_item(0, "db_updated"), _item(1, "pending")]
    item, action = mig.tree_next(items, _status({}))
    assert item["topo_index"] == 1 and action == "start_move"


def test_tree_release_phase_only_after_all_committed():
    # one still moving -> NOT in release phase yet
    items = [_item(0, "db_updated"), _item(1, "moving", move_task_id="m")]
    item, action = mig.tree_next(items, _status({"m": "started"}))
    assert item["topo_index"] == 1 and action == "wait"
    # all committed -> release phase begins (sources deleted last)
    items = [_item(0, "db_updated"), _item(1, "db_updated")]
    item, action = mig.tree_next(items, _status({}))
    assert action == "release"


def test_tree_blocked_on_failure():
    items = [_item(0, "failed"), _item(1, "pending")]
    item, action = mig.tree_next(items, _status({}))
    assert action == "blocked" and item["topo_index"] == 0


def test_tree_done_when_all_released():
    items = [_item(0, "released"), _item(1, "released")]
    item, action = mig.tree_next(items, _status({}))
    assert item is None and action == "done"


def test_tree_skipped_items_are_terminal():
    items = [_item(0, "released"), _item(1, "skipped")]
    item, action = mig.tree_next(items, _status({}))
    assert item is None and action == "done"


def test_release_phase_picks_committed_items():
    items = [_item(0, "released"), _item(1, "db_updated")]
    item, action = mig.tree_next(items, _status({}))
    assert item["topo_index"] == 1 and action == "release"
