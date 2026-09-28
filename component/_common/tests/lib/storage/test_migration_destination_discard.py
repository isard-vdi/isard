# SPDX-License-Identifier: AGPL-3.0-or-later

"""An abandoned tree leaves no copy behind on the destination: mock-only."""

import pytest
from isardvdi_common.lib.storage import migration_run as mr

SRC_DIR = "/pool-src"
DST_DIR = "/pool-dst"


class _Row:
    directory_path = SRC_DIR


class _Storage:
    rows = {}

    @classmethod
    def exists(cls, sid):
        return sid in cls.rows

    def __init__(self, sid):
        self.directory_path = _Storage.rows[sid]

    @staticmethod
    def update_document(*a, **k):
        pass


def _runner(monkeypatch, *, drainable=True, system_action="delete", verify=True):
    r = object.__new__(mr.MigrationRunner)
    r.migration_id = "m1"
    r.config = {"verify": verify, "source_disposition": "system"}
    r.user_id = "admin"
    r.lane_is_drainable = lambda conn, queue: drainable
    r._system_delete_action = lambda: system_action
    caps = {"enqueued": []}

    def _enqueue(task, queue, kwargs, timeout=None):
        caps["enqueued"].append((task, queue, kwargs))
        return "tid"

    r._enqueue = _enqueue
    r._set = lambda item, **f: item.update(f)
    r._pool_queue = lambda path, action: f"storage.{path.split('/')[1]}.{action}"
    r._restore_domains = lambda item: None
    monkeypatch.setattr(mr, "Storage", _Storage)
    return r, caps


def _item(sid, state, **extra):
    it = {
        "id": f"i-{sid}",
        "state": state,
        "storage_id": sid,
        "tree_id": "t1",
        "kind": "desktop",
        "src_path": f"{SRC_DIR}/{sid}.qcow2",
        "dst_path": f"{DST_DIR}/{sid}.qcow2",
        "dst_dir": DST_DIR,
        "size_bytes": 10,
        "storage_orig_status": None,
    }
    it.update(extra)
    return it


@pytest.mark.parametrize("state", ["moving", "moved", "rebased"])
def test_cancel_discards_the_copy_of_a_disk_that_reached_the_destination(
    monkeypatch, state
):
    """Cancelled at 72 % of a large batch, the disks mid-flight had their copy on
    the destination and their row back on the source: nothing named the copy and
    nothing removed it."""
    _Storage.rows = {"a": SRC_DIR}
    r, caps = _runner(monkeypatch)
    item = _item("a", state, dst_owned=True)

    r._cancel_skip_tree([item], "canceled before tree committed")

    assert caps["enqueued"] == [
        ("delete", "storage.pool-dst.delete", {"path": item["dst_path"]})
    ]
    assert item["state"] == "skipped"
    assert item["dst_action"] == "delete"
    assert item["audit"][-1]["dst_action"] == "delete"


@pytest.mark.parametrize("state", ["pending", "preflight_ok"])
def test_cancel_leaves_alone_a_disk_that_never_copied(monkeypatch, state):
    _Storage.rows = {"a": SRC_DIR}
    r, caps = _runner(monkeypatch)
    item = _item("a", state)

    r._cancel_skip_tree([item], "canceled")

    assert caps["enqueued"] == []
    assert item.get("dst_action") is None


def test_a_committed_disk_keeps_its_destination_whatever_the_state_says(monkeypatch):
    """The row already points at the destination: that file is the live disk."""
    _Storage.rows = {"a": DST_DIR}
    r, caps = _runner(monkeypatch)
    item = _item("a", "db_updated")

    r._cancel_skip_tree([item], "canceled")

    assert caps["enqueued"] == []
    assert item.get("dst_action") is None


def test_the_destination_follows_the_same_disposition_as_the_source(monkeypatch):
    _Storage.rows = {"a": SRC_DIR}
    r, caps = _runner(monkeypatch, system_action="move")
    item = _item("a", "moved", dst_owned=True)

    r._cancel_skip_tree([item], "canceled")

    assert [t for t, _q, _k in caps["enqueued"]] == ["move_delete"]
    assert item["dst_action"] == "move_delete"


def test_a_dead_destination_lane_records_the_retained_copy(monkeypatch):
    _Storage.rows = {"a": SRC_DIR}
    r, caps = _runner(monkeypatch, drainable=False)
    item = _item("a", "moved", dst_owned=True)

    r._cancel_skip_tree([item], "canceled")

    assert caps["enqueued"] == []
    assert item["dst_retained"] is True
    assert item["dst_retained_path"] == item["dst_path"]
    assert item["audit"][-1]["dst_retained_path"] == item["dst_path"]


def test_a_failed_tree_discards_the_copies_of_its_abandoned_disks(monkeypatch):
    """The failing disk and the abandoned ones in its tree all leave the copy
    they had made on the destination, exactly like a cancel."""
    _Storage.rows = {"root": DST_DIR, "a": SRC_DIR, "b": SRC_DIR}
    r, caps = _runner(monkeypatch)
    root = _item("root", "db_updated")  # committed ancestor: row on destination
    a = _item("a", "moved", parent_storage_id="root", dst_owned=True)
    b = _item("b", "pending", parent_storage_id="root")
    r._items = lambda: [root, a, b]
    r._failure_reason = lambda item: "verify said no"

    r._terminalize_tree_failure(a)

    assert [(t, k["path"]) for t, _q, k in caps["enqueued"]] == [
        ("delete", a["dst_path"])
    ]
    assert a["state"] == "failed" and b["state"] == "skipped"
    assert root.get("dst_action") is None


@pytest.mark.parametrize("state", ["moving", "moved", "rebased"])
def test_a_destination_the_attempt_never_proved_clear_is_kept(monkeypatch, state):
    """Unproven destination files are recorded, never discarded."""
    _Storage.rows = {"a": SRC_DIR}
    r, caps = _runner(monkeypatch)
    item = _item("a", state)

    r._cancel_skip_tree([item], "canceled")

    assert caps["enqueued"] == [], "a file this attempt did not write was discarded"
    assert item["dst_retained"] is True
    assert item["dst_retained_path"] == item["dst_path"]
    assert item.get("dst_action") is None


def test_a_move_that_failed_before_writing_keeps_the_file_it_found(monkeypatch):
    """A move that failed on a missing source keeps the file found at the destination."""
    _Storage.rows = {"a": SRC_DIR}
    r, caps = _runner(monkeypatch)
    item = _item("a", "moving", move_task_id="t-move")
    r._items = lambda: [item]
    r._failure_reason = lambda it: "ValueError: Path /pool-src/a.qcow2 not found"

    r._terminalize_tree_failure(item)

    assert caps["enqueued"] == [], "the disk's only copy was sent to be deleted"
    assert item["state"] == "failed"
    assert item["dst_retained_path"] == item["dst_path"]


def test_a_rearm_forgets_that_the_destination_was_ours(monkeypatch):
    _Storage.rows = {"a": SRC_DIR}
    r, caps = _runner(monkeypatch)
    item = _item("a", "failed", dst_owned=True)

    r._rearm_item(item, 1)

    assert item["state"] == "pending"
    assert item["dst_owned"] is False
