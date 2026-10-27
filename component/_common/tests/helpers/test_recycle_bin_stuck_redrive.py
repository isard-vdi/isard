#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Releasing entries already stranded mid-delete.

Two independent gaps keep an entry in ``deleting`` for ever once a first delete
attempt failed:

1. A re-drive of ``delete_storage`` APPENDS its fresh task rows to the ones the
   failed attempt left behind. ``update_task_status`` only flips the entry to
   ``deleted`` when ``len(finished) == len(tasks)``, so a lingering non-finished
   row (a ``failed`` delete) makes that count never match: the re-drive deletes
   the disk yet the entry stays ``deleting`` until a later pass finds the disk
   already gone. A drive must judge its completion by its OWN task set.

2. Nothing automatic re-drives a ``deleting`` entry: the startup reconcile only
   re-enqueues ``queued``. An install that upgrades past the fixes never empties
   the entries it was already carrying unless an admin runs recover-stuck by
   hand. Startup must also re-enqueue entries long stranded in ``deleting``.

Both tests drive the real code and assert only on observable behaviour (the task
rows left on the entry; which ids the startup reconcile enqueues). They name no
symbol the fix introduces, so they collect and run against the unfixed module
and go red there.
"""

import asyncio
from unittest.mock import MagicMock

import pytest


def _chain(result):
    """A rethink query chain (.get_all(...).pluck(...)[...] .run()) -> ``result``."""
    m = MagicMock(name="query")
    m.get_all.return_value = m
    m.pluck.return_value = m
    m.filter.return_value = m
    m.__getitem__.return_value = m
    m.run.return_value = result
    return m


@pytest.fixture
def redrive(monkeypatch):
    """The real ``delete_storage`` re-driven over an entry already in
    ``deleting`` that still carries ONE live storage and a stale ``failed`` task
    from the attempt that stranded it. ``inner.tasks`` is a real list so the test
    can see exactly which rows the drive leaves on the entry."""
    import isardvdi_common.helpers.recycle_bin as mod
    from isardvdi_common.lib import governor_counters, queue_coverage

    Real = mod.RecycleBin
    seen = {"events": [], "statuses": [], "logs": []}

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(
        queue_coverage,
        "lane_shed_decision",
        lambda conn, queue, now=None: (
            "ok",
            {"pool": "p", "category": "cat-1", "tier": "reclaim", "has_consumer": True},
        ),
    )
    monkeypatch.setattr(
        governor_counters, "record_shed", lambda *a, **k: None, raising=False
    )

    monkeypatch.setattr(mod.RecycleBin, "_rdb_context", lambda self: _Ctx())
    monkeypatch.setattr(
        type(mod.RecycleBin),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
        raising=False,
    )
    monkeypatch.setattr(mod.r, "table", lambda name: _chain(["ready"]))
    monkeypatch.setattr(mod.r, "args", lambda x: x)

    inner = Real.__new__(Real)
    inner.id = "rb-1"
    inner.owner_id = "owner-1"
    inner.storages = [{"id": "s1"}]
    inner.tasks = [
        {"id": "stale", "item_id": "s1", "item_type": "storage", "status": "failed"}
    ]
    inner._add_task = lambda payload: inner.tasks.append(payload)
    inner._reset_tasks = lambda: inner.tasks.clear()
    monkeypatch.setattr(mod, "RecycleBin", lambda _id: inner)

    storage = MagicMock(name="storage-s1")
    storage.id = "s1"
    storage.status = "ready"
    storage.path = "/pool-a/s1.qcow2"
    storage.directory_path = "/pool-a"
    storage.category = "cat-1"

    class FakeStorage:
        exists = staticmethod(lambda sid: True)
        get_children = staticmethod(lambda ids, include_deleted=False: [])

        def __new__(cls, sid):
            return storage

    monkeypatch.setattr(mod, "Storage", FakeStorage)

    pool = MagicMock(name="pool")
    pool.id = "pool-a"
    monkeypatch.setattr(
        mod.StoragePool,
        "get_best_for_action",
        staticmethod(lambda action, path=None, **k: pool),
    )
    monkeypatch.setattr(
        mod.StoragePool, "mountpoint_for_path", staticmethod(lambda *a, **k: None)
    )
    monkeypatch.setattr(
        mod.queue_tiers,
        "retier_queue",
        lambda base, task, cat=None: f"{base.rsplit('.', 1)[0]}.{cat}.reclaim",
    )
    monkeypatch.setattr(
        mod.Helpers, "get_delete_action", staticmethod(lambda: "delete")
    )

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

    rb = Real.__new__(Real)
    rb.status = "deleting"
    rb.users = []
    rb.storages = [{"id": "s1"}]
    rb.categories = rb.groups = []
    rb.owner_id = "owner-1"
    rb.id = "rb-1"
    rb.agent_type = rb.agent_id = rb.agent_name = None
    rb.agent_category_id = rb.agent_category_name = rb.agent_role = None
    rb._update_agent = lambda user_id: None
    rb.dependent_storages = lambda: []
    return mod, seen, inner, rb


class TestRedriveStartsAFreshTaskSet:
    def test_a_redrive_does_not_keep_the_prior_attempts_task_rows(self, redrive):
        """The disk still needs deleting, so the entry is re-driven to
        ``deleting`` and a fresh delete task is placed — but the stale ``failed``
        row from the attempt that stranded it must not survive, or the entry can
        never again satisfy len(finished) == len(tasks)."""
        mod, seen, inner, rb = redrive

        rb.delete_storage("agent-user")

        # A fresh delete task was placed for the live disk.
        assert ("create", "s1") in seen["events"]
        assert seen["statuses"][-1] == "deleting"
        # The entry carries ONLY this drive's task now; the stale failed row is gone.
        assert [t["status"] for t in inner.tasks] == ["queued"]
        assert all(t["id"] != "stale" for t in inner.tasks)


class TestStartupReconcileDrainsStaleDeleting:
    @pytest.mark.asyncio
    async def test_initialize_reenqueues_stale_deleting_not_only_queued(
        self, monkeypatch
    ):
        """On startup the queue must pick up entries long stranded in
        ``deleting`` too, so an upgraded install empties them without an admin
        running recover-stuck by hand."""
        from isardvdi_common.helpers.recycle_bin import RecycleBinDeleteQueue

        q = RecycleBinDeleteQueue.__new__(RecycleBinDeleteQueue)
        q._initialized = False
        monkeypatch.setattr(RecycleBinDeleteQueue, "_lock", None, raising=False)
        monkeypatch.setattr(
            q, "_queued_entries", lambda: [{"id": "q1", "agent_id": "u1"}]
        )
        monkeypatch.setattr(
            q,
            "_stale_deleting_entries",
            lambda: [{"id": "d1", "agent_id": "u2"}],
            raising=False,
        )
        enqueued = []

        async def fake_enqueue(item):
            enqueued.append(item["recycle_bin_id"])
            return True

        monkeypatch.setattr(q, "enqueue", fake_enqueue)

        await q.initialize()

        assert "q1" in enqueued
        assert "d1" in enqueued
