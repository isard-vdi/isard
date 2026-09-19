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
