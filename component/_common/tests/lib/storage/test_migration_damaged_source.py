# SPDX-License-Identifier: AGPL-3.0-or-later

"""A source that fails its integrity check is marked damaged, and the job pauses
or goes on by its own knob: mock-only, no DB, no redis."""

import pytest
from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.lib.storage import migration_run as mr


def test_damage_is_read_off_the_verify_gates_error():
    line = f"{mig.DAMAGED_SOURCE_MARK} /p/s.qcow2: corruptions=62 leaks=0"
    assert mig.damage_from_reason(line) == "/p/s.qcow2: corruptions=62 leaks=0"
    # as the runner really sees it: the traceback's last line
    assert (
        mig.damage_from_reason("RuntimeError: " + line)
        == "/p/s.qcow2: corruptions=62 leaks=0"
    )
    assert (
        mig.damage_from_reason("migration: destination /p/d.qcow2 did not pass") is None
    )
    assert mig.damage_from_reason(None) is None


def test_a_fully_terminal_tree_no_longer_blocks():
    """A tree whose disks are all failed or skipped kept yielding ``blocked`` on
    every tick, and under failure_policy=pause that re-paused the job the moment
    it was resumed. Terminal work is done, not blocked."""
    items = [
        {"id": "a", "state": "failed", "topo_index": 0},
        {"id": "b", "state": "skipped", "topo_index": 1},
    ]
    assert mig.tree_next(items, lambda tid: None) == (None, "done")


def test_a_tree_with_a_failed_disk_and_live_siblings_still_blocks():
    items = [
        {"id": "a", "state": "failed", "topo_index": 0},
        {"id": "b", "state": "pending", "topo_index": 1},
    ]
    item, action = mig.tree_next(items, lambda tid: None)
    assert (item["id"], action) == ("a", "blocked")


class _Storage:
    writes = []

    @classmethod
    def exists(cls, sid):
        return True

    def __init__(self, sid):
        self.directory_path = "/src"

    @classmethod
    def update_document(cls, sid, fields, validate=True):
        cls.writes.append((sid, dict(fields)))


def _runner(monkeypatch, reason):
    r = object.__new__(mr.MigrationRunner)
    r.migration_id = "m1"
    r.config = {}
    r.user_id = "admin"
    r.lane_is_drainable = lambda conn, queue: True
    r._enqueue = lambda task, queue, kwargs, timeout=None: "tid"
    r._set = lambda item, **f: item.update(f)
    r._pool_queue = lambda path, action: "q"
    r._restore_domains = lambda item: None
    r._failure_reason = lambda item: reason
    r._system_delete_action = lambda: "move"
    _Storage.writes = []
    monkeypatch.setattr(mr, "Storage", _Storage)
    return r


def _item(sid, state, **extra):
    it = {
        "id": f"i-{sid}",
        "state": state,
        "storage_id": sid,
        "tree_id": "t1",
        "kind": "desktop",
        "src_path": f"/src/{sid}.qcow2",
        "dst_path": f"/dst/{sid}.qcow2",
        "dst_dir": "/dst",
        "size_bytes": 10,
        "storage_orig_status": "ready",
    }
    it.update(extra)
    return it


def test_a_damaged_source_is_marked_and_the_reason_kept(monkeypatch):
    r = _runner(
        monkeypatch, f"{mig.DAMAGED_SOURCE_MARK} /src/a.qcow2: corruptions=62 leaks=0"
    )
    a = _item("a", "rebased", verify_task_id="v")
    r._items = lambda: [a]

    r._terminalize_tree_failure(a)

    assert a["state"] == "failed"
    assert a["damaged"] is True and "corruptions=62" in a["damage_reason"]
    # the LAST write wins: the restore to the original status runs first
    assert _Storage.writes[-1] == (
        "a",
        {"status": "damaged", "damage_reason": "/src/a.qcow2: corruptions=62 leaks=0"},
    )
    assert a["audit"][-1]["damaged"] is True
    assert sum(1 for rec in a["audit"] if rec["storage_id"] == "a") == 1


def test_a_copy_failure_marks_nothing_damaged(monkeypatch):
    r = _runner(
        monkeypatch,
        "migration: destination /dst/a.qcow2 did not pass qemu-img check (corruptions=3)",
    )
    a = _item("a", "rebased", verify_task_id="v")
    r._items = lambda: [a]

    r._terminalize_tree_failure(a)

    assert a["state"] == "failed" and not a.get("damaged")
    assert all(f.get("status") != "damaged" for _s, f in _Storage.writes)


def test_a_damaged_media_marks_no_storage_row(monkeypatch):
    r = _runner(monkeypatch, f"{mig.DAMAGED_SOURCE_MARK} /src/m.iso: rc=1")
    m = _item("m", "rebased", kind="media", verify_task_id="v")
    r._items = lambda: [m]

    r._terminalize_tree_failure(m)

    assert m["damaged"] is True
    assert _Storage.writes == []


# --------------------------------------------------------------------------- #
# on_damaged=repair_* : one in-flight repair, re-verify, continue-or-terminalize
# --------------------------------------------------------------------------- #


def _repair_runner(monkeypatch, reason, on_damaged):
    r = _runner(monkeypatch, reason)
    r.config = {"on_damaged": on_damaged}
    return r


def test_repair_leaks_enqueues_a_leak_repair_and_goes_repairing(monkeypatch):
    r = _repair_runner(
        monkeypatch,
        f"{mig.DAMAGED_SOURCE_MARK} /dst/a.qcow2: leaks=593",
        "repair_leaks",
    )
    a = _item("a", "rebased", verify_task_id="v")
    r._items = lambda: [a]

    r._fail(a)

    assert a["state"] == "repairing"
    assert a["repair_action"] == "leaks"
    assert a["repair_attempted"] is True
    assert a["repair_task_id"] == "tid"
    assert not a.get("damaged")


def test_repair_all_uses_check_r_all(monkeypatch):
    r = _repair_runner(
        monkeypatch,
        f"{mig.DAMAGED_SOURCE_MARK} /dst/a.qcow2: corruptions=4",
        "repair_all",
    )
    a = _item("a", "rebased", verify_task_id="v")
    r._items = lambda: [a]

    r._fail(a)

    assert a["state"] == "repairing" and a["repair_action"] == "all"


def test_repair_only_for_a_real_damage_not_a_copy_failure(monkeypatch):
    r = _repair_runner(
        monkeypatch, "migration: destination /dst/a.qcow2 did not pass", "repair_leaks"
    )
    a = _item("a", "rebased", verify_task_id="v")
    r._items = lambda: [a]

    r._fail(a)

    assert a["state"] == "failed"


def test_a_disk_is_repaired_at_most_once_then_terminalizes(monkeypatch):
    r = _repair_runner(
        monkeypatch, f"{mig.DAMAGED_SOURCE_MARK} /dst/a.qcow2: leaks=1", "repair_leaks"
    )
    a = _item("a", "rebased", verify_task_id="v", repair_attempted=True)
    r._items = lambda: [a]

    r._fail(a)

    assert a["state"] == "failed" and a["damaged"] is True


def test_repair_without_a_consumer_terminalizes(monkeypatch):
    r = _repair_runner(
        monkeypatch, f"{mig.DAMAGED_SOURCE_MARK} /dst/a.qcow2: leaks=1", "repair_leaks"
    )
    r.lane_is_drainable = lambda conn, queue: False
    a = _item("a", "rebased", verify_task_id="v")
    r._items = lambda: [a]

    r._fail(a)

    assert a["state"] == "failed"


class _RepairTask:
    def __init__(self, tid):
        self._id = tid

    @property
    def result(self):
        return {"ok": True, "summary": "repaired"}


def test_mark_repaired_sends_the_disk_back_through_verify(monkeypatch):
    r = _repair_runner(monkeypatch, "x", "repair_leaks")
    monkeypatch.setattr(mr, "Task", _RepairTask)
    a = _item(
        "a", "repairing", repair_task_id="rt", verify_task_id="oldv", verify_passed=True
    )
    r._items = lambda: [a]

    r._mark_repaired(a)

    assert a["state"] == "rebased"
    assert a["verify_task_id"] is None and a["verify_passed"] is False
    assert a["repair_result"] == {"ok": True, "summary": "repaired"}


def test_tree_next_holds_a_repairing_disk_until_the_repair_settles():
    items = [_item("a", "repairing", repair_task_id="rt")]
    assert mig.tree_next(items, lambda tid: "started")[1] == "wait"
    assert mig.tree_next(items, lambda tid: "finished")[1] == "mark_repaired"
    assert mig.tree_next(items, lambda tid: "failed")[1] == "repair_failed"
