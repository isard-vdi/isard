# SPDX-License-Identifier: AGPL-3.0-or-later

"""A migration must never leave work looking placed when it could not place it.

The runner is the one storage producer that never passes through ``create_task``,
so nothing above it refuses an enqueue onto a lane with no live worker. Two
different things then go wrong, and they want two different answers.

Before the tree is committed (rebase, verify) the right answer is to DEFER: the
outage is transient, the disk keeps its state, the next tick retries. What must
not happen is a half-step -- a claim fence written and a job pushed onto a lane
nothing drains. ``tree_next`` waits on that job, only a STARTED task can be
orphaned and re-driven, so a queued-for-ever one wedges the tree: the migration
never completes and ``reactivate()`` never restores autostart.

After the tree is committed (release) deferring is the wrong answer: the row
already points at the destination and the disks are out of maintenance, so
holding the release hostage to a pool outage keeps every desktop in the migration
down for as long as the outage lasts. There the answer is to complete and RECORD
that the source file was left behind, because once the row moves nothing else
names that path.

These tests drive the runner with mocks only (no DB, no redis), in the style of
the neighbouring claim tests: the lane verdict is forced on the instance, so they
collect and run against the version that has no gate at all.
"""

import isardvdi_common.lib.storage.migration_run as mr

SRC = "/pool-src/disk.qcow2"
DST = "/pool-dst/disk.qcow2"


def _runner(*, drainable):
    """A runner with nothing behind it and one forced answer about the lane.

    ``lane_is_drainable`` is shadowed on the INSTANCE rather than patched on the
    class, so this harness says nothing about how (or whether) the runner asks.
    """
    r = object.__new__(mr.MigrationRunner)
    r.migration_id = "m1"
    r.config = {}
    r.user_id = "admin"
    r.lane_is_drainable = lambda conn, queue: drainable
    return r


def _instrument(r, *, pool_queue="storage.p-src.default"):
    """Capture every enqueue and every ledger write, and neutralise the rest."""
    caps = {"enqueued": [], "writes": [], "claims": []}

    def _enqueue(task, queue, kwargs, timeout=None):
        caps["enqueued"].append((task, queue, kwargs))
        return "real-tid"

    def _set(item, **fields):
        caps["writes"].append(dict(fields))
        item.update(fields)

    r._enqueue = _enqueue
    r._set = _set
    r._pool_queue = lambda path: pool_queue
    r._claim_storage_task = lambda item, task_id: None
    return caps


def _fake_claim(monkeypatch, item, caps):
    """Faithful CAS: the when-clause is evaluated against the live item."""

    def _claim(cls, item_id, *, when, set_fields):
        caps["claims"].append(dict(set_fields))
        if all(item.get(k) == v for k, v in when.items()):
            item.update(set_fields)
            return True
        return False

    monkeypatch.setattr(mr.StorageMigrationItem, "claim", classmethod(_claim))


def _fences(caps, field):
    """Every ``claim:`` value ever written to ``field``, claims and sets alike."""
    return [
        value
        for written in caps["claims"] + caps["writes"]
        for key, value in written.items()
        if key == field and str(value).startswith("claim:")
    ]


# _release — committed tree: complete, and record the source we could not delete
def test_release_onto_a_dead_lane_records_the_retained_source(monkeypatch):
    """A source pool with no worker leaves the old file on disk for ever with
    nothing naming it: the row already points at the destination, so the only
    thing that would have removed it is a move_delete queued where nobody
    listens, and no operator is ever told which path to reclaim by hand."""
    item = {
        "id": "i1",
        "state": "db_updated",
        "storage_id": "s1",
        "tree_id": "t1",
        "kind": "desktop",
        "src_path": SRC,
        "dst_path": DST,
        "size_bytes": 1024,
        "move_delete_task_id": None,
        "storage_orig_status": None,  # never put into maintenance -> no restore
    }
    r = _runner(drainable=False)
    caps = _instrument(r)

    r._release(item)

    assert caps["enqueued"] == [], "a delete was handed to a lane nothing drains"
    assert item["state"] == "released"
    assert item.get("move_delete_task_id") is None
    assert item.get("source_retained") is True
    assert item.get("source_retained_path") == SRC
    record = (item.get("audit") or [])[-1]
    # still moved_ok: a new result string would drop the disk out of the audit total.
    assert record["result"] == "moved_ok"
    assert record.get("source_retained") is True
    assert record.get("source_retained_path") == SRC


def test_release_deletes_the_source_on_the_reclaim_lane():
    """A source delete left on the foreground default lane makes a mass
    migration's thousands of unlinks compete with desktop starts, instead of
    trailing behind them on the tier deletes are floored to."""
    item = {
        "id": "i1",
        "state": "db_updated",
        "storage_id": "s1",
        "tree_id": "t1",
        "kind": "desktop",
        "src_path": SRC,
        "dst_path": DST,
        "size_bytes": 1024,
        "move_delete_task_id": None,
        "storage_orig_status": None,
    }
    r = _runner(drainable=True)
    caps = _instrument(r)

    r._release(item)

    assert len(caps["enqueued"]) == 1
    action, queue, kwargs = caps["enqueued"][0]
    assert action == "move_delete"
    assert queue.endswith(".reclaim"), f"the delete went to {queue}"
    assert kwargs == {"path": SRC}
    assert item["state"] == "released"
    assert item["move_delete_task_id"] == "real-tid"
    assert not item.get("source_retained"), "a placed delete must retain nothing"


# _start_rebase / _start_verify — uncommitted tree: defer BEFORE the claim
def test_start_rebase_onto_a_dead_lane_leaves_no_fence_behind(monkeypatch):
    """A rebase pushed onto an undrainable lane wedges the whole tree: nothing
    takes it, nothing raises, no timeout fires, and tree_next waits on a task
    that only a STARTED one could be orphaned and re-driven from -- so the
    migration never completes and autostart is never restored. Writing the claim
    fence first makes it worse: the next tick sees a reserved slot instead of a
    fresh disk."""
    item = {
        "id": "i1",
        "state": "moved",
        "storage_id": "s1",
        "dst_path": DST,
        "parent_dst_path": "/pool-dst/parent.qcow2",
        "rebase_task_id": None,
    }
    r = _runner(drainable=False)
    caps = _instrument(r, pool_queue="storage.p-dst.default")
    _fake_claim(monkeypatch, item, caps)

    r._start_rebase(item)

    assert caps["enqueued"] == [], "a rebase was handed to a lane nothing drains"
    assert item["state"] == "moved", "the disk advanced on an unplaceable job"
    assert caps["claims"] == [], "the ledger was claimed before the lane was asked"
    assert _fences(caps, "rebase_task_id") == [], "a fence outlived a deferred tick"


def test_start_verify_onto_a_dead_lane_leaves_no_fence_behind(monkeypatch):
    """Same wedge one phase later, and this one holds the pre-release gate: the
    tree cannot reach release until every destination verifies, so a verify
    parked on a lane with no worker freezes the migration with every disk still
    in maintenance and every source still on disk."""
    item = {
        "id": "i1",
        "state": "rebased",
        "storage_id": "s1",
        "dst_path": DST,
        "parent_dst_path": "/pool-dst/parent.qcow2",
        "verify_task_id": None,
    }
    r = _runner(drainable=False)
    caps = _instrument(r, pool_queue="storage.p-dst.default")
    _fake_claim(monkeypatch, item, caps)

    r._start_verify(item)

    assert caps["enqueued"] == [], "a verify was handed to a lane nothing drains"
    assert item["state"] == "rebased", "the disk advanced on an unplaceable job"
    assert caps["claims"] == [], "the ledger was claimed before the lane was asked"
    assert _fences(caps, "verify_task_id") == [], "a fence outlived a deferred tick"
