# SPDX-License-Identifier: AGPL-3.0-or-later

"""``Storage.recreate`` asks the create lane before it parks the disk.

The park (``set_maintenance``) is recreate's first mutation. When the lane was only
asked later, inside ``create_task``, a refusal there left the row parked naming no
task and the reconcile backstop finalized it to ``deleted``. A non-allocating
``check_shed`` ahead of the park refuses while the disk is still Ready, so nothing is
parked and the user retries. The refused case means something only against its
control -- the admitted case -- so both are pinned here.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models import storage as mod
from isardvdi_common.models.storage import Storage


@pytest.fixture
def rec(monkeypatch):
    """An old Ready disk whose recreate collaborators record their order, with a
    knob to make the lane admission (``check_shed``) refuse."""
    events = []
    holder = {"shed_error": None}

    old = Storage.__new__(Storage)
    old.__dict__.update(
        {
            "id": "old-1",
            "user_id": "u-1",
            "type": "qcow2",
            "parent": "tmpl-1",
            "path": "/isard/groups/old-1.qcow2",
            "directory_path": "/isard/groups",
            "status": "ready",
            "status_logs": [{"time": 1, "status": "created"}],
        }
    )

    monkeypatch.setattr(
        Storage,
        "__setattr__",
        lambda self, name, value: self.__dict__.__setitem__(name, value),
    )
    monkeypatch.setattr(Storage, "operational", True)
    monkeypatch.setattr(Storage, "pool_usage", "desktop")
    monkeypatch.setattr(Storage, "category", "cat-1")
    monkeypatch.setattr(Storage, "domains", [])
    monkeypatch.setattr(Storage, "exists", staticmethod(lambda _id: True))
    monkeypatch.setattr(mod.qcow2_geometry, "policy", staticmethod(lambda: {}))
    monkeypatch.setattr(
        mod.StoragePool,
        "get_best_for_action",
        staticmethod(lambda *a, **k: MagicMock(id="pool-1")),
    )
    monkeypatch.setattr(
        mod, "new_storage_directory_path", staticmethod(lambda *a, **k: "/isard/groups")
    )
    monkeypatch.setattr(
        mod.queue_tiers, "retier_queue", staticmethod(lambda q, t, c: q)
    )
    monkeypatch.setattr(mod.queue_tiers, "resolve_category", staticmethod(lambda c: c))

    # ``Storage(<parent>)`` reads the parent row.
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

    def _check_shed(conn, queue):
        events.append(("admit", queue))
        if holder["shed_error"] is not None:
            raise holder["shed_error"]

    monkeypatch.setattr(mod.queue_coverage, "check_shed", _check_shed)

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

    monkeypatch.setattr(Storage, "set_maintenance", _set_maintenance)

    def _create_task(self, *a, **k):
        events.append(("task",))
        return "task-1"

    monkeypatch.setattr(Storage, "create_task", _create_task)
    monkeypatch.setattr(
        Storage, "delete_document_if", staticmethod(lambda *a, **k: True)
    )
    return SimpleNamespace(old=old, events=events, holder=holder)


class TestRecreateAdmitsBeforePark:
    def test_admitted_lane_admits_then_parks_then_allocates_then_tasks(self, rec):
        # Control: the lane accepts, so the admission runs first and recreate proceeds.
        assert rec.old.recreate("u-1", "dom-1") == "task-1"
        assert [e[0] for e in rec.events] == ["admit", "park", "alloc", "task"]

    def test_a_refused_lane_parks_nothing_and_allocates_nothing(self, rec):
        # A refused lane must raise before the park: nothing parked, nothing allocated.
        rec.holder["shed_error"] = Error(
            "too_many_requests",
            "Storage lane pool-1/standard is temporarily unable to accept work",
            description_code="storage_no_consumer_retry_later",
        )
        with pytest.raises(Error) as exc:
            rec.old.recreate("u-1", "dom-1")
        assert exc.value.error["description_code"] == "storage_no_consumer_retry_later"
        assert [e[0] for e in rec.events] == ["admit"]
        assert not [e for e in rec.events if e[0] in ("park", "alloc", "task")]
