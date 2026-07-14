# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the per-disk migration saga DECISION layer (pure).

These pin the correctness-critical ordering invariants:
  * top-to-bottom, strictly serial within a tree (one disk in flight),
  * a child only starts once its parent has been moved+rebased (``rebased``) so
    the child's rebase target — the parent's file at its new path — exists,
  * the root never rebases,
  * the DB commit (db_update) is DEFERRED until AFTER the whole tree's
    pre-release verify gate passes, so a gate failure never leaves a row on a
    bad/unverified destination (F1),
  * source deletion (release) happens only AFTER every row is committed
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


def test_rebased_is_phase_a_done_no_more_move_work():
    # F1: ``rebased`` (moved + backing repointed) ends Phase A. The DB commit
    # (db_update) is DEFERRED to Phase B, past the verify gate — so a rebased
    # disk has no further per-disk Phase-A action.
    it = _item(1, "rebased")
    assert mig.decide_item_action(it, _status({})) == "noop"


# --------------------------------------------------------------------------- #
# F1: the storage row is NOT repointed to the destination (db_update) until the
# pre-release verify gate PASSES. A disk whose destination fails verification
# must never have reached db_updated — so terminalizing the tree leaves every
# row pointing at its retained source (never at the bad/unverified destination).
# --------------------------------------------------------------------------- #
def test_db_update_deferred_until_destination_verified():
    it = _item(0, "rebased", src_path="/a/r.qcow2", dst_path="/b/r.qcow2")
    # moved+rebased but NOT yet verified -> drive the gate, never a db_update
    # that would commit the row to an unverified destination.
    assert mig.tree_next([it], _status({}))[1] == "start_verify"
    it["verify_task_id"] = "v"
    assert mig.tree_next([it], _status({"v": "started"}))[1] == "wait"
    # gate FAILED -> fail; db_update was never issued, so the row still points at
    # the retained source.
    assert mig.tree_next([it], _status({"v": "failed"}))[1] == "fail"
    # gate PASSED -> only NOW is the row repointed (db_update).
    assert mig.tree_next([it], _status({"v": "finished"}))[1] == "db_update"


def test_failed_verify_never_commits_row_to_destination():
    # There must be NO saga path where a disk reaches db_updated with an
    # unverified destination: a rebased disk whose gate has already failed goes
    # straight to fail, never db_update.
    it = _item(
        0, "rebased", src_path="/a/r.qcow2", dst_path="/b/r.qcow2", verify_task_id="v"
    )
    assert mig.tree_next([it], _status({"v": "failed"}))[1] == "fail"


# --------------------------------------------------------------------------- #
# saga-1: dst == src — same-pool selection, or a subtree member already living
# in the destination pool. The move is a no-op and the release would
# move_delete the LIVE disk in place (total data loss), so both are skipped.
# --------------------------------------------------------------------------- #
def test_pending_in_place_skips_move():
    it = _item(0, "pending", src_path="/pool/r.qcow2", dst_path="/pool/r.qcow2")
    assert mig.decide_item_action(it, _status({})) == "skip_move"


def test_pending_cross_location_still_moves():
    it = _item(0, "pending", src_path="/a/r.qcow2", dst_path="/b/r.qcow2")
    assert mig.decide_item_action(it, _status({})) == "start_move"


def test_release_skipped_when_disk_in_place():
    items = [_item(0, "db_updated", src_path="/pool/r.qcow2", dst_path="/pool/r.qcow2")]
    item, action = mig.tree_next(items, _status({}))
    assert action == "skip_release" and item["topo_index"] == 0


def test_release_deletes_source_when_moved_elsewhere():
    items = [_item(0, "rebased", src_path="/a/r.qcow2", dst_path="/b/r.qcow2")]
    # the row is repointed (db_update) only AFTER the destination passes the
    # verify gate, and the source is move_deleted only after that.
    assert mig.tree_next(items, _status({}))[1] == "start_verify"
    items[0]["verify_task_id"] = "v"
    assert mig.tree_next(items, _status({"v": "finished"}))[1] == "db_update"
    items[0]["state"] = "db_updated"
    assert mig.tree_next(items, _status({"v": "finished"}))[1] == "release"


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
    # root moved+rebased (Phase A done) -> child may now start; the parent's
    # file already sits at its new path, so the child's rebase target exists
    # (the parent's DB commit is deferred to Phase B).
    items = [_item(0, "rebased"), _item(1, "pending")]
    item, action = mig.tree_next(items, _status({}))
    assert item["topo_index"] == 1 and action == "start_move"


def test_tree_release_phase_only_after_all_committed():
    # one still moving -> NOT in Phase B yet
    items = [_item(0, "rebased"), _item(1, "moving", move_task_id="m")]
    item, action = mig.tree_next(items, _status({"m": "started"}))
    assert item["topo_index"] == 1 and action == "wait"
    # all moved+rebased -> Phase B begins with the unconditional destination
    # gate (start_verify), BEFORE any db_update/release
    items = [_item(0, "rebased"), _item(1, "rebased")]
    item, action = mig.tree_next(items, _status({}))
    assert action == "start_verify"


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
    items = [_item(0, "released"), _item(1, "rebased")]
    item, action = mig.tree_next(items, _status({}))
    # the moved+rebased disk enters Phase B at its destination gate
    assert item["topo_index"] == 1 and action == "start_verify"
