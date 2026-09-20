# SPDX-License-Identifier: AGPL-3.0-or-later

"""The pre-move destination gate: a migration never adopts a file already at the
destination.

``move`` copies with ``rsync -a``, whose quick-check SKIPS a destination whose
size and mtime match the source. A complete orphan a prior (pre-source_disposition)
cancel/failure left, or one this stack retained, is exactly such a file, so a
re-run would copy nothing, the post-move verify gate would bless the stale copy,
and consolidation would rest on bytes the current run never produced.

The runner cannot stat the pools (only the storage worker mounts them), so before
enqueuing the move it enqueues a read-only ``migration_verify_destination_absent``
check on the destination pool's worker; a disk stays ``pending`` until it clears.
An occupied destination fails the disk with ``destination_exists: <path>`` without
touching anything, records the retained path for the census, and lets
``failure_policy`` decide the job.
"""

import isardvdi_common.lib.storage.migration_run as mr
from isardvdi_common.lib import queue_tiers
from isardvdi_common.lib.storage import migration as mig

SRC_DIR = "/pool-src"
DST_DIR = "/pool-dst"


def _item(state, **extra):
    it = {
        "id": "i1",
        "state": state,
        "storage_id": "s1",
        "tree_id": "t1",
        "kind": "desktop",
        "src_path": f"{SRC_DIR}/s1.qcow2",
        "dst_path": f"{DST_DIR}/s1.qcow2",
        "dst_dir": DST_DIR,
        "size_bytes": 10,
        "preflight_task_id": None,
        "storage_orig_status": None,
    }
    it.update(extra)
    return it


def _status(mapping):
    return lambda tid: mapping.get(tid)


# --------------------------------------------------------------------------- #
# decide_item_action — a pending disk checks the destination before it moves
# --------------------------------------------------------------------------- #
def test_fresh_pending_starts_the_preflight_not_the_move():
    # The regression: on the old code a cross-location pending disk went
    # straight to start_move, so rsync -a could adopt an orphan. Now it checks.
    assert mig.decide_item_action(_item("pending"), _status({})) == "start_preflight"


def test_preflight_still_running_waits():
    it = _item("pending", preflight_task_id="p1")
    assert mig.decide_item_action(it, _status({"p1": "started"})) == "wait"


def test_preflight_clear_lets_the_move_start():
    it = _item("pending", preflight_task_id="p1")
    assert mig.decide_item_action(it, _status({"p1": "finished"})) == "start_move"


def test_preflight_finding_a_file_refuses_the_disk():
    it = _item("pending", preflight_task_id="p1")
    assert mig.decide_item_action(it, _status({"p1": "failed"})) == "destination_exists"


def test_lost_preflight_job_is_reenqueued():
    # The read-only stat is idempotent, so a job lost on a restart re-enqueues.
    it = _item("pending", preflight_task_id="gone")
    assert mig.decide_item_action(it, _status({})) == "start_preflight"


def test_in_place_disk_skips_the_preflight_entirely():
    # dst == src: the "destination" IS the live disk; a preflight would refuse a
    # legitimate same-pool selection. It must skip the move, never check.
    it = _item("pending", src_path="/p/s1.qcow2", dst_path="/p/s1.qcow2")
    assert mig.decide_item_action(it, _status({})) == "skip_move"


def test_tree_next_yields_destination_exists_for_a_blocked_pending_root():
    # Driven through tree_next (the real ordering entry point), a pending root
    # whose destination check failed surfaces the refusal, not a move.
    it = _item("pending", preflight_task_id="p1")
    item, action = mig.tree_next([it], _status({"p1": "failed"}))
    assert item["id"] == "i1" and action == "destination_exists"


# --------------------------------------------------------------------------- #
# _start_preflight — enqueues the read-only check on the DESTINATION worker
# --------------------------------------------------------------------------- #
def _runner(*, drainable=True):
    r = object.__new__(mr.MigrationRunner)
    r.migration_id = "m1"
    r.config = {}
    r.user_id = "admin"
    r.lane_is_drainable = lambda conn, queue: drainable
    caps = {"enqueued": [], "writes": [], "claims": []}

    def _enqueue(task, queue, kwargs, timeout=None):
        caps["enqueued"].append((task, queue, kwargs))
        return "real-tid"

    def _set(item, **fields):
        caps["writes"].append(dict(fields))
        item.update(fields)

    r._enqueue = _enqueue
    r._set = _set
    # Use the real tier rules so a step that mis-names its action is visible.
    r._pool_queue = lambda path, action: queue_tiers.retier_queue(
        f"storage.{path.split('/')[1]}.default", action
    )
    r._claim_storage_task = lambda item, task_id: None
    r._restore_domains = lambda item: None
    return r, caps


def _fake_claim(monkeypatch, item, caps):
    def _claim(cls, item_id, *, when, set_fields):
        caps["claims"].append(dict(set_fields))
        if all(item.get(k) == v for k, v in when.items()):
            item.update(set_fields)
            return True
        return False

    monkeypatch.setattr(mr.StorageMigrationItem, "claim", classmethod(_claim))


def test_start_preflight_enqueues_the_absent_check_on_the_destination_lane(monkeypatch):
    r, caps = _runner(drainable=True)
    item = _item("pending")
    _fake_claim(monkeypatch, item, caps)

    r._start_preflight(item)

    assert len(caps["enqueued"]) == 1
    task, queue, kwargs = caps["enqueued"][0]
    assert task == "migration_verify_destination_absent"
    assert kwargs == {"dst_path": f"{DST_DIR}/s1.qcow2"}
    # the check runs on the DESTINATION pool, on the governed maintenance lane
    # (never the reserved interactive pool)
    assert queue == "storage.pool-dst.maintenance"
    assert item["state"] == "pending", "the disk must not leave pending to check"
    assert item["preflight_task_id"] == "real-tid"


def test_start_preflight_defers_on_a_dead_destination_lane(monkeypatch):
    r, caps = _runner(drainable=False)
    item = _item("pending")
    _fake_claim(monkeypatch, item, caps)

    r._start_preflight(item)

    assert caps["enqueued"] == [], "a check was handed to a lane nothing drains"
    assert caps["claims"] == [], "the ledger was claimed before the lane was asked"
    assert item["preflight_task_id"] is None


# --------------------------------------------------------------------------- #
# _destination_exists — refuse untouched, record the path, terminalize the tree
# --------------------------------------------------------------------------- #
def test_destination_exists_fails_the_disk_without_touching_anything(monkeypatch):
    r, caps = _runner()
    item = _item("pending")
    r._items = lambda: [item]
    monkeypatch.setattr(
        mr, "Storage", type("S", (), {"exists": staticmethod(lambda s: False)})
    )

    r._destination_exists(item)

    assert item["state"] == "failed"
    assert item["error"] == f"destination_exists: {DST_DIR}/s1.qcow2"
    # the orphan is flagged for the census, never adopted and never deleted
    assert item["dst_retained_path"] == f"{DST_DIR}/s1.qcow2"
    assert caps["enqueued"] == [], "the pre-existing file must not be touched"
    assert item["audit"][-1]["result"] == "failed"
