#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``delete_storage`` must not place a permanent delete on a lane nothing can
drain — and when it cannot place one, it must not leave the entry looking
placed.

An entry only reaches ``deleted`` once EVERY one of its storages finished, so a
delete enqueued into a lane with no worker parks the entry in ``deleting``
forever: the disks are still on the pool, the bin shows a deletion in progress,
and the only exit is an admin running the stuck-entry recovery. The entry has to
go back to ``recycled`` — the state a normal delete re-drives — with nothing
enqueued at all, and the deferral has to be auditable.

These tests drive the real ``delete_storage`` (nothing about the function under
test is mocked) and assert only on what an operator can observe: which tasks
were built, what was registered on the entry, the status the entry was left in,
and the log line appended. They deliberately name no symbol the fix introduced,
so they COLLECT and RUN against the unfixed module and go red there.
"""

from unittest.mock import MagicMock

import pytest


def _chain(result):
    """A rethink query chain (.get_all(...).pluck(...)[...] .run()) that yields
    ``result``."""
    m = MagicMock(name="query")
    m.get_all.return_value = m
    m.pluck.return_value = m
    m.__getitem__.return_value = m
    m.run.return_value = result
    return m


@pytest.fixture
def harness(monkeypatch):
    """The real ``delete_storage`` driven over an entry with TWO live storages
    on TWO different pools, with each lane's verdict under the test's control.

    ``lane["dead"]`` holds the queue names that have no consumer. The verdict is
    applied by patching ``queue_coverage.lane_shed_decision`` — the ONE decision
    both postures of the gate share, and the only piece of it that predates the
    fix, so this fixture builds identically on a module that never consults the
    gate at all.
    """
    import isardvdi_common.helpers.recycle_bin as mod
    from isardvdi_common.lib import governor_counters, queue_coverage

    Real = mod.RecycleBin  # keep the real class; the factory below shadows the name
    seen = {"events": [], "statuses": [], "logs": [], "sheds": []}
    lane = {"dead": set(), "reason": "no_consumer"}

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    # --- the lane verdict, at the level that exists with or without the fix.
    def fake_decision(conn, queue, now=None):
        ctx = {"pool": queue.split(".")[1], "category": "cat-1", "tier": "reclaim"}
        if queue in lane["dead"]:
            return "reject", dict(ctx, reason=lane["reason"], has_consumer=False)
        return "ok", dict(ctx, reason=None, has_consumer=True)

    monkeypatch.setattr(queue_coverage, "lane_shed_decision", fake_decision)
    monkeypatch.setattr(
        governor_counters,
        "record_shed",
        lambda conn, reason, pool=None, tier=None, now=None: seen["sheds"].append(
            reason
        ),
    )

    # --- rethink layer: the only DB read per entry is the storages' status;
    #     two non-"deleted" statuses -> the "still has live disks" branch.
    monkeypatch.setattr(mod.RecycleBin, "_rdb_context", lambda self: _Ctx())
    monkeypatch.setattr(
        type(mod.RecycleBin),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
        raising=False,
    )
    monkeypatch.setattr(mod.r, "table", lambda name: _chain(["ready", "ready"]))
    monkeypatch.setattr(mod.r, "args", lambda x: x)

    # --- the inner RecycleBin(entry["id"]) load -> a controlled bare entry with
    #     two live storages; record what gets registered on it.
    inner = Real.__new__(Real)
    inner.id = "rb-1"
    inner.owner_id = "owner-1"
    inner.storages = [{"id": "s1"}, {"id": "s2"}]
    inner._add_task = lambda payload: seen["events"].append(
        ("register", payload["item_id"])
    )
    monkeypatch.setattr(mod, "RecycleBin", lambda _id: inner)

    # --- Storage: the code uses BOTH Storage.exists(id) and Storage(id). The
    #     two disks live on different pools, so they resolve to different lanes.
    storages = {}
    for sid, directory in (("s1", "/pool-a"), ("s2", "/pool-b")):
        storage = MagicMock(name="storage-" + sid)
        storage.id = sid
        storage.status = "ready"
        storage.path = f"{directory}/{sid}.qcow2"
        storage.directory_path = directory
        storage.category = "cat-1"
        storages[sid] = storage

    class FakeStorage:
        exists = staticmethod(lambda sid: True)

        def __new__(cls, sid):
            return storages[sid]

    monkeypatch.setattr(mod, "Storage", FakeStorage)

    # --- pool + queue tiering: one pool per directory, reclaim tier per storage.
    def fake_best_for_action(action, path=None, **kwargs):
        pool = MagicMock(name="pool")
        pool.id = str(path).strip("/")
        return pool

    monkeypatch.setattr(
        mod.StoragePool, "get_best_for_action", staticmethod(fake_best_for_action)
    )
    monkeypatch.setattr(
        mod.queue_tiers,
        "retier_queue",
        lambda base, task, cat=None: f"{base.rsplit('.', 1)[0]}.{cat}.reclaim",
    )
    monkeypatch.setattr(
        mod.Helpers, "get_delete_action", staticmethod(lambda: "delete")
    )

    # --- Task: record every construction, and hand back a job that records its
    #     own enqueue, so create -> register -> enqueue order is observable.
    def fake_task(*a, **k):
        sid = k.get("storage_id")
        seen["events"].append(("create", sid))
        task = MagicMock(name="task-" + str(sid))
        task.id = "task-" + str(sid)
        task.status = "queued"
        task.enqueue = lambda: seen["events"].append(("enqueue", task.id))
        return task

    fake_task._redis = MagicMock(name="redis")
    monkeypatch.setattr(mod, "Task", fake_task)

    # --- side-effect helpers -> recorders.
    monkeypatch.setattr(
        mod.Helpers,
        "update_status",
        staticmethod(lambda rid, oid, status: seen["statuses"].append(status)),
    )
    monkeypatch.setattr(
        mod.Helpers,
        "add_log",
        staticmethod(lambda name, *a, **k: seen["logs"].append(name)),
    )
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)

    # the OUTER entry whose delete_storage() we drive (built from the real class)
    rb = Real.__new__(Real)
    rb.status = "recycled"
    rb.users = []
    rb.storages = [{"id": "s1"}, {"id": "s2"}]
    rb.categories = rb.groups = []
    rb.owner_id = "owner-1"
    rb.id = "rb-1"
    rb.agent_type = rb.agent_id = rb.agent_name = None
    rb.agent_category_id = rb.agent_category_name = rb.agent_role = None
    rb._update_agent = lambda user_id: None
    rb.dependent_storages = lambda: []
    return mod, seen, lane, rb


class TestDeadLaneDefersTheWholeEntry:
    def test_no_consumer_places_nothing_and_leaves_the_entry_recycled(self, harness):
        """A pool whose workers are gone would otherwise park the entry in
        ``deleting`` forever: disks still on the pool, the bin showing a
        deletion in progress, and no exit but admin stuck-entry recovery."""
        mod, seen, lane, rb = harness
        lane["dead"] = {"storage.pool-a.cat-1.reclaim", "storage.pool-b.cat-1.reclaim"}

        tasks = rb.delete_storage("agent-user")

        # Nothing built, nothing registered on the entry, nothing enqueued.
        assert seen["events"] == []
        assert tasks == []
        # The entry is back where a normal delete re-drives it, and it was never
        # written as "deleting" on the way there.
        assert "deleting" not in seen["statuses"]
        assert seen["statuses"][-1] == "recycled"
        # And the deferral is auditable rather than silent.
        assert "delete_deferred" in seen["logs"]
        assert "deleting" not in seen["logs"]

    def test_one_dead_lane_holds_back_the_storages_whose_lanes_are_alive(self, harness):
        """Enqueueing only the storages that CAN run is the same stuck entry:
        it can never reach ``deleted`` with one delete missing, so a single dead
        pool has to defer the whole entry, not its own disk."""
        mod, seen, lane, rb = harness
        lane["dead"] = {"storage.pool-b.cat-1.reclaim"}  # s1's pool is healthy

        rb.delete_storage("agent-user")

        assert [event for event in seen["events"] if event[0] == "create"] == []
        assert seen["statuses"][-1] == "recycled"
        assert "delete_deferred" in seen["logs"]


class TestHealthyLaneIsUnchanged:
    def test_every_storage_is_created_registered_then_enqueued(self, harness):
        """The highest-volume storage producer: if this gate ever refuses a
        healthy lane, no disk in the fleet is ever reclaimed again."""
        mod, seen, lane, rb = harness
        lane["dead"] = set()

        tasks = rb.delete_storage("agent-user")

        # Registered on the entry BEFORE enqueue: the ordering that closes the
        # lost-completion window.
        assert seen["events"] == [
            ("create", "s1"),
            ("register", "s1"),
            ("enqueue", "task-s1"),
            ("create", "s2"),
            ("register", "s2"),
            ("enqueue", "task-s2"),
        ]
        assert [task["storage_id"] for task in tasks] == ["s1", "s2"]
        assert seen["statuses"] == ["deleting"]
        assert seen["logs"] == ["deleting"]
        assert seen["sheds"] == []


class TestTypedErrorIsNotLaundered:
    def test_a_428_from_an_inner_call_propagates_as_a_428(self, harness, monkeypatch):
        """A typed refusal rewritten as a 500 tells the operator the server
        broke instead of what is wrong and what to retry — the same laundering
        that would hide a lane refusal from every synchronous caller of the
        permanent delete."""
        mod, seen, lane, rb = harness
        from isardvdi_common.helpers.recycle_bin import Error

        def refuse(*a, **k):
            raise Error(
                "precondition_required",
                "Storage pool cannot serve delete",
            )

        # Raised from INSIDE delete_storage's try block, where the catch-all
        # rewrites everything it sees.
        monkeypatch.setattr(
            mod.StoragePool, "get_best_for_action", staticmethod(refuse)
        )

        with pytest.raises(Error) as exc:
            rb.delete_storage("agent-user")

        assert exc.value.status_code == 428
        assert exc.value.error["error"] == "precondition_required"
        assert "Storage pool cannot serve delete" in exc.value.error["description"]
