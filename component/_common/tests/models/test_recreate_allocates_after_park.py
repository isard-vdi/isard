# SPDX-License-Identifier: AGPL-3.0-or-later

"""``Storage.recreate`` parks before it allocates, and undoes the allocation.

Two things are pinned: a refused precondition writes no storage row at all, and a
row allocated before the task is refused is removed again. ``set_maintenance`` is
the only step that validates the row's own status, so allocating ahead of it left
an unreferenced ``non_existing`` row behind on every refused call, and nothing
retires that status.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models import storage as mod
from isardvdi_common.models.storage import Storage


@pytest.fixture
def rec(monkeypatch):
    """An old disk whose recreate collaborators are stubbed and whose
    allocate/park/task/rollback record their order."""
    events = []
    holder = {"park_error": None, "task_error": None}

    old = Storage.__new__(Storage)
    old.__dict__.update(
        {
            "id": "old-1",
            "user_id": "u-1",
            "type": "qcow2",
            "parent": "tmpl-1",
            "path": "/isard/groups/old-1.qcow2",
            "directory_path": "/isard/groups",
            "status": "deleted",
            "status_logs": [{"time": 1, "status": "created"}],
        }
    )

    # Every attribute write on a Storage is a DB update; keep them in memory.
    monkeypatch.setattr(
        Storage,
        "__setattr__",
        lambda self, name, value: self.__dict__.__setitem__(name, value),
    )
    # Properties that would query the DB.
    monkeypatch.setattr(Storage, "operational", True)
    monkeypatch.setattr(Storage, "pool_usage", "desktop")
    monkeypatch.setattr(Storage, "category", "cat-1")
    # ``domains`` is a property that queries the domains table; the FAILED branch
    # of the chain definition walks it.
    monkeypatch.setattr(Storage, "domains", [])
    monkeypatch.setattr(Storage, "exists", staticmethod(lambda _id: True))
    monkeypatch.setattr(mod.qcow2_geometry, "policy", staticmethod(lambda: {}))
    monkeypatch.setattr(
        mod.StoragePool,
        "get_best_for_action",
        staticmethod(lambda *a, **k: MagicMock(id="pool-1")),
    )
    # recreate resolves the create lane and asks check_shed before parking; stub
    # both so these tests exercise only the park/allocate/task ordering they pin.
    monkeypatch.setattr(
        mod, "new_storage_directory_path", staticmethod(lambda *a, **k: "/isard/groups")
    )
    monkeypatch.setattr(mod.queue_coverage, "check_shed", lambda *a, **k: None)

    # ``Storage(<id>)`` reads the row; hand back a bare object with the fields
    # ``recreate`` actually touches on the parent.
    def _init(self, sid=None, *a, **k):
        self.__dict__.update(
            {
                "id": sid,
                "type": "qcow2",
                "directory_path": "/isard/templates",
                "parent": None,
            }
        )

    monkeypatch.setattr(Storage, "__init__", _init)

    def _new_dict(user_id, pool_usage, parent_id=None, format="qcow2"):
        events.append(("alloc",))
        new = Storage.__new__(Storage)
        new.__dict__.update(
            {
                "id": "new-1",
                "user_id": user_id,
                "type": format,
                "status": "non_existing",
                "parent": parent_id,
                "directory_path": "/isard/groups",
                "status_logs": [],
            }
        )
        return new

    monkeypatch.setattr(Storage, "new_dict", staticmethod(_new_dict))

    def _set_maintenance(self, action="system maintenance", exclude_domains=None):
        events.append(("park", action))
        if holder["park_error"] is not None:
            raise holder["park_error"]

    monkeypatch.setattr(Storage, "set_maintenance", _set_maintenance)

    def _create_task(self, *a, **k):
        events.append(("task",))
        if holder["task_error"] is not None:
            raise holder["task_error"]
        return "task-1"

    monkeypatch.setattr(Storage, "create_task", _create_task)

    def _delete_document_if(document_id, *, field, values):
        events.append(("rollback", document_id, field, tuple(values)))
        return True

    monkeypatch.setattr(
        Storage, "delete_document_if", staticmethod(_delete_document_if)
    )

    return SimpleNamespace(old=old, events=events, holder=holder)


def _not_ready():
    return Error(
        "precondition_required",
        "Storage old-1 must be Ready in order to operate with it. It's actual status is deleted",
        description_code="storage_not_ready",
    )


class TestRecreateAllocatesAfterPark:
    def test_parks_before_allocating(self, rec):
        assert rec.old.recreate("u-1", "dom-1") == "task-1"
        assert [e[0] for e in rec.events] == ["park", "alloc", "task"]

    def test_a_refused_park_allocates_nothing(self, rec):
        rec.holder["park_error"] = _not_ready()
        with pytest.raises(Error) as exc:
            rec.old.recreate("u-1", "dom-1")
        assert exc.value.error["description_code"] == "storage_not_ready"
        # The whole point: no row was written, so there is nothing to leak.
        assert [e[0] for e in rec.events] == ["park"]
        assert not [e for e in rec.events if e[0] == "alloc"]

    def test_a_refused_task_removes_the_row_it_allocated(self, rec):
        rec.holder["task_error"] = Error(
            "precondition_required",
            "Storage old-1 has the pending task find-1",
            description_code="storage_pending_task",
        )
        with pytest.raises(Error):
            rec.old.recreate("u-1", "dom-1")
        rollbacks = [e for e in rec.events if e[0] == "rollback"]
        assert rollbacks == [("rollback", "new-1", "status", ("non_existing",))]

    def test_a_shed_refusal_removes_the_row_too(self, rec):
        # The rollback is not keyed on the exception type: enforce_shed raises its
        # own typed 429 inside create_task, once the row already exists.
        rec.holder["task_error"] = RuntimeError("no live consumer on that lane")
        with pytest.raises(RuntimeError):
            rec.old.recreate("u-1", "dom-1")
        assert [e for e in rec.events if e[0] == "rollback"] == [
            ("rollback", "new-1", "status", ("non_existing",))
        ]

    def test_the_happy_path_keeps_the_row(self, rec):
        rec.old.recreate("u-1", "dom-1")
        assert not [e for e in rec.events if e[0] == "rollback"]
