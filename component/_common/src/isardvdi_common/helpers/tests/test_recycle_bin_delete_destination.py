#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``delete_storage`` must send the disk to the destination the deployment
configured: a ``move_delete`` task (recoverable, moved aside) when the config
says ``move``, and a hard ``delete`` task otherwise.

This is the one path where getting the *destination* wrong loses data
silently — a ``delete`` where the operator asked for ``move`` shreds a disk
they expected to keep. The test drives the real ``delete_storage`` (no mock of
the function under test) and asserts on the ``task`` name of the Task it
enqueues.
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
def driven(monkeypatch):
    import isardvdi_common.helpers.recycle_bin as mod

    Real = mod.RecycleBin  # keep the real class; the factory below shadows the name
    captured = {}

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    # --- rethink layer: the only DB read delete_storage does per entry is the
    #     storages' status; return one non-"deleted" status so it takes the
    #     "still has live disks" branch that queues the delete/move task.
    monkeypatch.setattr(mod.RecycleBin, "_rdb_context", lambda self: _Ctx())
    monkeypatch.setattr(
        type(mod.RecycleBin),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
        raising=False,
    )
    monkeypatch.setattr(mod.r, "table", lambda name: _chain(["ready"]))
    monkeypatch.setattr(mod.r, "args", lambda x: x)

    # --- the inner RecycleBin(entry["id"]) load -> a controlled bare entry with
    #     one live storage; record the tasks it registers.
    inner = Real.__new__(Real)
    inner.id = "rb-1"
    inner.owner_id = "owner-1"
    inner.storages = [{"id": "s1"}]
    inner._add_task = lambda payload: captured.setdefault("registered", payload)
    monkeypatch.setattr(mod, "RecycleBin", lambda _id: inner)

    # --- Storage: the code uses BOTH Storage.exists(id) and Storage(id), so the
    #     stand-in needs the staticmethod AND to construct into a live disk.
    storage = MagicMock(name="storage")
    storage.id = "s1"
    storage.status = "ready"
    storage.path = "/pool/s1.qcow2"
    storage.directory_path = "/pool"
    storage.category = "cat-1"

    class FakeStorage:
        exists = staticmethod(lambda sid: True)

        def __new__(cls, sid):
            return storage

    monkeypatch.setattr(mod, "Storage", FakeStorage)

    # --- pool + queue tiering: irrelevant to the destination, stub them.
    pool = MagicMock()
    pool.id = "pool-1"
    monkeypatch.setattr(
        mod.StoragePool, "get_best_for_action", staticmethod(lambda *a, **k: pool)
    )
    monkeypatch.setattr(
        mod.queue_tiers, "retier_queue", lambda base, task, cat: f"q:{task}"
    )

    # --- Task: capture the task name (the thing under test) and behave enqueue-able.
    def fake_task(*a, **k):
        captured["task_name"] = k.get("task")
        captured["queue"] = k.get("queue")
        t = MagicMock(name="task")
        t.id = "task-1"
        t.status = "queued"
        return t

    monkeypatch.setattr(mod, "Task", fake_task)

    # --- misc side-effect helpers -> no-ops.
    monkeypatch.setattr(
        mod.Helpers, "update_status", staticmethod(lambda *a, **k: None)
    )
    monkeypatch.setattr(mod.Helpers, "add_log", staticmethod(lambda *a, **k: None))
    monkeypatch.setattr(mod.time, "sleep", lambda *_: None)

    # the OUTER entry whose delete_storage() we drive (built from the real class)
    rb = Real.__new__(Real)
    rb.status = "recycled"
    rb.users = []
    rb.storages = [{"id": "s1"}]
    rb.categories = rb.groups = []
    rb.owner_id = "owner-1"
    rb.id = "rb-1"
    rb.agent_type = rb.agent_id = rb.agent_name = None
    rb.agent_category_id = rb.agent_category_name = rb.agent_role = None
    rb._update_agent = lambda user_id: None
    rb.dependent_storages = lambda: []
    return mod, captured, rb


class TestDeleteStorageDestination:
    def test_move_config_queues_a_move_delete_task(self, driven):
        mod, captured, rb = driven
        mod.Helpers.get_delete_action = staticmethod(lambda: "move")
        rb.delete_storage("agent-user")
        assert captured["task_name"] == "move_delete"

    def test_delete_config_queues_a_hard_delete_task(self, driven):
        mod, captured, rb = driven
        mod.Helpers.get_delete_action = staticmethod(lambda: "delete")
        rb.delete_storage("agent-user")
        assert captured["task_name"] == "delete"
