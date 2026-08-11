# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the recurring re-scan / failure-policy / audit DECISION layer
(pure). These pin, decoupled from the DB reconciler:

  * ``should_rescan`` — the three cadences (edge / edge_on_drain / continuous),
  * ``plan_tree_rearm`` — per-tree re-arm vs quarantine at an occurrence edge
    under each failure policy (a quarantined disk kills its tree; a failed disk
    that hits the budget is quarantined; otherwise failed/skipped disks re-arm),
  * ``build_audit_record`` / ``summarize_audit`` — the downloadable-log records
    and their summary header.
"""

from isardvdi_common.lib.storage import migration as mig


# --------------------------------------------------------------------------- #
# should_rescan — cadence
# --------------------------------------------------------------------------- #
def test_rescan_never_outside_window():
    for cadence in ("edge", "edge_on_drain", "continuous"):
        assert mig.should_rescan(cadence, "k2", "k1", True, False) is False


def test_rescan_edge_only_at_occurrence_edge():
    assert mig.should_rescan("edge", "k2", "k1", False, True) is True  # new key
    assert mig.should_rescan("edge", "k1", "k1", True, True) is False  # same key


def test_rescan_edge_on_drain():
    # same occurrence, not drained -> no re-scan
    assert mig.should_rescan("edge_on_drain", "k1", "k1", False, True) is False
    # same occurrence but the batch drained -> re-scan to pick up new disks
    assert mig.should_rescan("edge_on_drain", "k1", "k1", True, True) is True
    # a fresh edge always re-scans
    assert mig.should_rescan("edge_on_drain", "k2", "k1", False, True) is True


def test_rescan_continuous_every_tick_in_window():
    assert mig.should_rescan("continuous", "k1", "k1", False, True) is True
    assert mig.should_rescan("continuous", "k1", "k1", True, True) is True


# --------------------------------------------------------------------------- #
# plan_tree_rearm — quarantine vs re-arm at an occurrence edge
# --------------------------------------------------------------------------- #
def _it(sid, state, occ=0, tree="r"):
    return {
        "id": f"m--{sid}",
        "storage_id": sid,
        "tree_id": tree,
        "state": state,
        "occurrence_failures": occ,
    }


def test_rearm_rearms_failed_and_skipped():
    tree = [_it("a", "failed", occ=1), _it("b", "skipped")]
    q, rearm = mig.plan_tree_rearm(tree, "retry_quarantine", 3)
    assert q == []
    got = {it["storage_id"]: occ for it, occ in rearm}
    assert got == {"a": 2, "b": 0}  # failed +1, skipped resets the streak


def test_rearm_quarantines_failed_at_budget():
    # a disk on its 3rd consecutive occurrence failure hits quarantine_after=3
    tree = [_it("a", "failed", occ=2), _it("b", "skipped")]
    q, rearm = mig.plan_tree_rearm(tree, "retry_quarantine", 3)
    assert [it["storage_id"] for it, _ in q] == ["a"]
    assert q[0][1] == 3
    assert rearm == []  # the tree is dead -> nothing re-armed around a stuck disk


def test_rearm_retry_forever_never_quarantines():
    tree = [_it("a", "failed", occ=99)]
    q, rearm = mig.plan_tree_rearm(tree, "retry_forever", 3)
    assert q == []
    assert rearm[0][1] == 100  # keeps counting but re-arms forever


def test_rearm_pause_policy_rearms_no_quarantine():
    tree = [_it("a", "failed", occ=99)]
    q, rearm = mig.plan_tree_rearm(tree, "pause", 3)
    assert q == []
    assert [it["storage_id"] for it, _ in rearm] == ["a"]


def test_rearm_dead_tree_with_quarantined_disk_untouched():
    tree = [_it("a", "quarantined", occ=3), _it("b", "skipped")]
    q, rearm = mig.plan_tree_rearm(tree, "retry_quarantine", 3)
    assert q == [] and rearm == []  # already dead — never re-armed


def test_rearm_leaves_released_and_inflight():
    tree = [_it("a", "released"), _it("b", "moving"), _it("c", "skipped")]
    q, rearm = mig.plan_tree_rearm(tree, "retry_quarantine", 3)
    assert q == []
    assert [it["storage_id"] for it, _ in rearm] == ["c"]  # only the skipped one


# --------------------------------------------------------------------------- #
# build_audit_record / summarize_audit
# --------------------------------------------------------------------------- #
def test_build_audit_record_shape():
    item = {
        "storage_id": "s1",
        "kind": "desktop",
        "tree_id": "r",
        "src_path": "/old/s1.qcow2",
        "dst_path": "/new/s1.qcow2",
        "size_bytes": 100,
        "error": None,
        "move_started_at": 10.0,
    }
    rec = mig.build_audit_record(item, "moved_ok", "2026-07-03", 25.0)
    assert rec["result"] == "moved_ok"
    assert rec["storage_id"] == "s1"
    assert rec["src_path"] == "/old/s1.qcow2"
    assert rec["dst_path"] == "/new/s1.qcow2"
    assert rec["occurrence"] == "2026-07-03"
    assert rec["started_at"] == 10.0
    assert rec["finished_at"] == 25.0
    assert rec["size_bytes"] == 100


def test_summarize_audit():
    recs = [
        {
            "result": "moved_ok",
            "size_bytes": 100,
            "started_at": 1.0,
            "finished_at": 5.0,
            "occurrence": "d1",
        },
        {
            "result": "moved_ok",
            "size_bytes": 50,
            "started_at": 2.0,
            "finished_at": 9.0,
            "occurrence": "d1",
        },
        {
            "result": "failed",
            "size_bytes": 20,
            "started_at": 3.0,
            "finished_at": 4.0,
            "occurrence": "d2",
        },
        {"result": "in_place", "size_bytes": 0, "occurrence": "d2"},
    ]
    s = mig.summarize_audit(recs)
    assert s["records"] == 4
    assert s["counts"] == {"moved_ok": 2, "failed": 1, "in_place": 1}
    assert s["bytes_moved"] == 150  # only moved_ok counts
    assert s["occurrences"] == 2  # d1, d2
    assert s["duration_seconds"] == 8.0  # max finish 9 - min start 1


def test_summarize_audit_empty():
    s = mig.summarize_audit([])
    assert s["records"] == 0
    assert s["bytes_moved"] == 0
    assert s["duration_seconds"] is None
    assert s["occurrences"] == 0
