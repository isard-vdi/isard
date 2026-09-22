# SPDX-License-Identifier: AGPL-3.0-or-later

"""A re-armed disk must tell the move task not to trust the destination.

``_rearm_item`` says it leaves the next attempt "clean", but it leaves the copy
the failed attempt wrote on the destination in place. ``move`` then matches it
by name, size and mtime — rsync preserves mtime — returns 0 without copying, and
the retry reaches the integrity gate with the same file and fails identically.

So the re-arm marks the item ``recopy`` and ``_start_move`` carries that into the
task as ``trust_existing_destination: False``; a clean move clears the mark.
"""

from isardvdi_common.lib.storage import migration as mig
from isardvdi_common.lib.storage import migration_run as mr


def _item(sid="r", state="failed", **kw):
    base = {
        "id": f"m--{sid}",
        "migration_id": "m",
        "storage_id": sid,
        "tree_id": "r",
        "topo_index": 0,
        "state": state,
        "size_bytes": 10,
        "src_path": f"/src/{sid}.qcow2",
        "dst_path": f"/dst/{sid}.qcow2",
        "occurrence_failures": 0,
        "audit": [],
        "parent_dst_path": None,
    }
    base.update(kw)
    return base


def _runner(monkeypatch, items, enqueued):
    def _update(cls, iid, fields, validate=True):
        for it in items:
            if it["id"] == iid:
                it.update(fields)

    def _claim(cls, item_id, *, when, set_fields):
        for it in items:
            if it["id"] == item_id and all(it.get(k) == v for k, v in when.items()):
                it.update(set_fields)
                return True
        return False

    monkeypatch.setattr(
        mr.StorageMigrationItem, "update_document", classmethod(_update)
    )
    monkeypatch.setattr(mr.StorageMigrationItem, "claim", classmethod(_claim))
    monkeypatch.setattr(
        mr.StorageMigrationItem, "incr", classmethod(lambda cls, i, f, by=1: 1)
    )
    monkeypatch.setattr(
        mr.StorageMigrationItem, "dicts_by_migration", classmethod(lambda cls, m: items)
    )

    r = object.__new__(mr.MigrationRunner)
    r.migration_id = "m"
    r.migration = type("M", (), {"config": {}, "last_occurrence": None})()
    r.config = {}
    r.user_id = "admin"
    r._move_queue = lambda p: "q"
    r.lane_is_drainable = lambda redis, q: True
    r._claim_storage_task = lambda item, tid: None
    r._record_throughput = lambda item: None
    r._is_media = lambda item: False
    # The disk-preparation step reaches Storage and the domains; the decision
    # under test is what the move payload carries, not how the disk is quiesced.
    r._prepare_disk_for_move = lambda item: True

    def _enq(kind, queue, payload, timeout=None):
        enqueued.append((kind, payload))
        return "tid"

    r._enqueue = _enq
    return r


class TestRetryRecopies:
    def test_rearm_marks_the_item_for_a_real_copy(self, monkeypatch):
        items = [_item(state="failed")]
        r = _runner(monkeypatch, items, [])
        r._rearm_item(items[0], 2)
        assert items[0]["recopy"] is True
        assert items[0]["state"] == "pending"

    def test_a_rearmed_move_does_not_trust_the_destination(self, monkeypatch):
        enqueued = []
        items = [_item(state="pending", recopy=True)]
        r = _runner(monkeypatch, items, enqueued)
        r._start_move(items[0])
        assert enqueued, "the move must be enqueued"
        kind, payload = enqueued[0]
        assert kind == "move"
        assert payload["trust_existing_destination"] is False

    def test_a_first_attempt_keeps_the_idempotent_short_circuit(self, monkeypatch):
        enqueued = []
        items = [_item(state="pending")]
        r = _runner(monkeypatch, items, enqueued)
        r._start_move(items[0])
        assert enqueued[0][1]["trust_existing_destination"] is True

    def test_a_clean_move_clears_the_mark(self, monkeypatch):
        items = [_item(state="moving", recopy=True)]
        r = _runner(monkeypatch, items, [])
        r._mark_moved(items[0])
        assert items[0]["recopy"] is False
        assert items[0]["state"] == "moved"
