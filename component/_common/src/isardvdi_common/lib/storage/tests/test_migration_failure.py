# SPDX-License-Identifier: AGPL-3.0-or-later

"""Failure-path regression tests for the migration saga (qcow-1 / scheduler-1 /
qcow-3 / saga-5).

The happy-path tests never exercised a failed move/rebase, so four real wedges
went untested:
  * qcow-1: a "fail"/"blocked" task action had no handler -> silent no-op,
    disk stuck forever, job never terminal, autostart never restored.
  * scheduler-1: a single FAILED disk made the tree permanently "blocked";
    descendant_item_ids()/cascade existed but was never wired in.
  * qcow-3: a failed/blocked disk's storage stayed in "maintenance" -> the
    desktop was unstartable.
  * saga-5: _release hardcoded status "ready", un-binning a "recycled" disk.
"""

import isardvdi_common.lib.storage.migration_run as mr
from isardvdi_common.lib.storage import migration as mig


def _it(sid, parent, state, **kw):
    base = {
        "id": f"i-{sid}",
        "storage_id": sid,
        "tree_id": "s0",
        "topo_index": 0 if sid == "s0" else 1,
        "parent_storage_id": parent,
        "state": state,
    }
    base.update(kw)
    return base


# --------------------------------------------------------------------------- #
# plan_tree_failure (pure) — cascade-skip descendants + abandon the rest
# --------------------------------------------------------------------------- #
def test_plan_tree_failure_cascades_and_abandons():
    items = [
        _it("s0", None, "db_updated"),  # committed ancestor — abandoned
        _it("s1", "s0", "moving"),  # the disk that fails
        _it("s2", "s1", "pending"),  # descendant of the failed disk
        _it("s3", "s0", "pending"),  # sibling subtree — abandoned
    ]
    plan = {
        it["id"]: (state, why) for it, state, why in mig.plan_tree_failure(items, "s1")
    }
    assert plan["i-s1"][0] == "failed"
    assert plan["i-s2"][0] == "skipped"  # descendant
    assert plan["i-s0"][0] == "skipped"  # committed ancestor abandoned (source kept)
    assert plan["i-s3"][0] == "skipped"  # sibling abandoned
    # reasons distinguish descendants from the rest
    assert "ancestor" in plan["i-s2"][1]


def test_plan_tree_failure_leaves_terminal_disks_untouched():
    items = [
        _it("s0", None, "released"),  # already terminal
        _it("s1", "s0", "failed"),  # already failed (e.g. generic handler)
        _it("s2", "s1", "skipped"),  # already skipped
    ]
    # everything terminal already -> nothing to change
    assert mig.plan_tree_failure(items, "s1") == []


# --------------------------------------------------------------------------- #
# qcow-1: the executor MUST handle "fail" and "blocked" (not silently no-op)
# --------------------------------------------------------------------------- #
def test_actions_table_handles_fail_and_blocked():
    assert "fail" in mr.MigrationRunner._ACTIONS
    assert "blocked" in mr.MigrationRunner._ACTIONS


# --------------------------------------------------------------------------- #
# saga-5 / qcow-3: storage status is restored to the RECORDED original, and a
# disk we never put into maintenance is left untouched.
# --------------------------------------------------------------------------- #
def _runner():
    return object.__new__(mr.MigrationRunner)


def test_restore_storage_status_uses_recorded_original(monkeypatch):
    updates = []

    class _S:
        @classmethod
        def update_document(cls, sid, fields, validate=True):
            updates.append((sid, fields))

    monkeypatch.setattr(mr, "Storage", _S)
    # a recycled disk dragged into a subtree must be restored to recycled,
    # never hardcoded "ready" (which would un-bin it for a later purge).
    _runner()._restore_storage_status(
        {"storage_id": "s1", "storage_orig_status": "recycled"}
    )
    assert updates == [("s1", {"status": "recycled"})]


def test_restore_storage_status_skips_untouched_disk(monkeypatch):
    updates = []

    class _S:
        @classmethod
        def update_document(cls, sid, fields, validate=True):
            updates.append((sid, fields))

    monkeypatch.setattr(mr, "Storage", _S)
    # never put into maintenance (no recorded original) -> do not touch it
    _runner()._restore_storage_status({"storage_id": "s2"})
    assert updates == []


def test_terminalize_resets_storage_and_cascades(monkeypatch):
    items = [
        _it("s0", None, "db_updated", storage_orig_status="ready"),
        _it("s1", "s0", "moving", storage_orig_status="recycled"),  # fails
        _it("s2", "s1", "pending"),  # descendant, never touched
    ]
    item_updates = []
    storage_updates = []

    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "dicts_by_migration",
        classmethod(lambda cls, mid: items),
    )
    monkeypatch.setattr(
        mr.StorageMigrationItem,
        "update_document",
        classmethod(
            lambda cls, iid, fields, validate=True: item_updates.append((iid, fields))
        ),
    )

    class _S:
        @classmethod
        def update_document(cls, sid, fields, validate=True):
            storage_updates.append((sid, fields))

    monkeypatch.setattr(mr, "Storage", _S)

    r = _runner()
    r.migration_id = "m"
    r._terminalize_tree_failure(items[1])  # s1's task failed

    states = {iid: f["state"] for iid, f in item_updates if "state" in f}
    assert states["i-s1"] == "failed"
    assert states["i-s2"] == "skipped"  # cascade to descendant
    assert states["i-s0"] == "skipped"  # committed ancestor abandoned
    su = dict(storage_updates)
    # qcow-3 + saga-5: maintenance disks reset to their ORIGINAL status
    assert su["s1"] == {"status": "recycled"}
    assert su["s0"] == {"status": "ready"}
    assert "s2" not in su  # never in maintenance -> untouched
