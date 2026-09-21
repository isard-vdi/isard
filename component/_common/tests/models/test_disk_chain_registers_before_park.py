# SPDX-License-Identifier: AGPL-3.0-or-later

"""``enqueue_disk_creation_chain_for_domain`` registers its task BEFORE it parks
the row (#3391, the #2824 principle).

The producer used to park the domain (``CreatingDisk``) and the storage
(``maintenance``) and only THEN call ``create_task``, which is what registers the
task in the per-owner index. A reconcile tick landing in that gap saw a parked row
that named no task and re-issued work, so apiv4's own ``create_task`` was then
refused with ``428 storage_pending_task``. Registering first (``create_task`` with
``enqueue=False``, which writes the index in ``Task.__init__`` regardless) closes
the gap: from the moment the row is parked it already names its task, and the job
is only placed on its queue afterwards, so no worker can finish it before the park.

Also pins the two things that make the reorder safe:
* a refused admission (``create_task`` raises before returning) leaves the domain
  ``Creating`` and the storage un-parked — nothing was written yet;
* if the park raises between register and enqueue, the registered task is cancelled
  so no registered-but-unenqueued job is left to masquerade as live work.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models import storage as mod
from isardvdi_common.models.storage import Storage


def _bare_disk():
    disk = Storage.__new__(Storage)
    disk.__dict__.update({"id": "disk-1", "task": None})
    return disk


class TestCreateTaskDeferredHandle:
    """``create_task`` hands back the un-enqueued Task when ``enqueue=False`` and
    the task id (the unchanged contract) otherwise."""

    def _run(self, storage, **extra):
        def _task(*args, **kwargs):
            built = MagicMock()
            built.id = "job-1"
            return built

        with patch(
            "isardvdi_common.models.storage.Task", side_effect=_task
        ) as Task, patch(
            "isardvdi_common.models.storage.queue_coverage.enforce_shed"
        ), patch.object(
            Storage, "category", "cat-1"
        ), patch.object(
            Storage, "__setattr__", lambda self, name, value: None
        ):
            Task.exists.return_value = False
            Task._redis = MagicMock()
            return storage.create_task(
                user_id="u-1", queue="storage.pool.default", task="convert", **extra
            )

    def test_default_returns_the_task_id(self):
        assert self._run(_bare_disk()) == "job-1"

    def test_enqueue_false_returns_the_task_object(self):
        out = self._run(_bare_disk(), enqueue=False)
        assert not isinstance(out, str)
        assert out.id == "job-1"


@pytest.fixture
def chain(monkeypatch):
    """A ``Storage`` whose chain-enqueue collaborators are all stubbed and whose
    create_task/set_maintenance/domain-flip/enqueue/cancel record their order."""
    events = []
    holder = {"register_error": None}

    storage = Storage.__new__(Storage)
    storage.__dict__.update(
        {
            "id": "st-1",
            "user_id": "u-1",
            "type": "qcow2",
            "parent": None,
            "path": "/isard/groups/st-1.qcow2",
            "directory_path": "/isard/groups",
        }
    )
    monkeypatch.setattr(Storage, "pool", MagicMock(id="pool-1"))
    monkeypatch.setattr(Storage, "category", "cat-1")
    monkeypatch.setattr(Storage, "_preflight_lane", lambda self, *a, **k: None)
    monkeypatch.setattr(mod.qcow2_geometry, "policy", staticmethod(lambda: {}))
    monkeypatch.setattr(
        mod.queue_tiers, "retier_queue", staticmethod(lambda q, t, c: q)
    )
    monkeypatch.setattr(mod.queue_tiers, "resolve_category", staticmethod(lambda c: c))

    class _Dom:
        def __init__(self):
            self._status = "Creating"

        @property
        def status(self):
            return self._status

        @status.setter
        def status(self, value):
            events.append(("flip", value))
            self._status = value

    dom = _Dom()
    fake_domain = MagicMock()
    fake_domain.exists.return_value = True
    fake_domain.return_value = dom
    import isardvdi_common.models.domain as domainmod

    monkeypatch.setattr(domainmod, "Domain", fake_domain)

    def _set_maintenance(self, action="system maintenance", exclude_domains=None):
        events.append(("park", action))

    monkeypatch.setattr(Storage, "set_maintenance", _set_maintenance)

    task = MagicMock(name="task")
    task.id = "task-1"
    task.enqueue.side_effect = lambda: events.append(("enqueue",)) or task
    task.cancel.side_effect = lambda: events.append(("cancel",))

    def _create_task(self, *a, **k):
        events.append(("register", k.get("enqueue")))
        if holder["register_error"] is not None:
            raise holder["register_error"]
        return task

    monkeypatch.setattr(Storage, "create_task", _create_task)
    return SimpleNamespace(
        storage=storage, events=events, task=task, dom=dom, holder=holder
    )


class TestChainRegistersBeforePark:
    def test_registers_unenqueued_then_parks_then_enqueues_last(self, chain):
        result = chain.storage.enqueue_disk_creation_chain_for_domain(
            "dom-1", size="10G"
        )
        assert result == "task-1"
        assert [e[0] for e in chain.events] == ["register", "flip", "park", "enqueue"]
        assert chain.events[0] == ("register", False)
        assert ("flip", "CreatingDisk") in chain.events
        chain.task.enqueue.assert_called_once()
        chain.task.cancel.assert_not_called()

    def test_refused_admission_leaves_domain_creating_and_storage_unparked(self, chain):
        chain.holder["register_error"] = Error(
            "precondition_required",
            "Storage st-1 has the pending task find-1",
            description_code="storage_pending_task",
        )
        with pytest.raises(Error) as exc:
            chain.storage.enqueue_disk_creation_chain_for_domain("dom-1", size="10G")
        assert exc.value.error["description_code"] == "storage_pending_task"
        assert [e[0] for e in chain.events] == ["register"]
        assert chain.dom._status == "Creating"
        chain.task.enqueue.assert_not_called()

    def test_park_failure_cancels_the_registered_task(self, chain, monkeypatch):
        def _boom(self, action="system maintenance", exclude_domains=None):
            chain.events.append(("park", action))
            raise RuntimeError("db down mid-park")

        monkeypatch.setattr(Storage, "set_maintenance", _boom)
        with pytest.raises(RuntimeError):
            chain.storage.enqueue_disk_creation_chain_for_domain("dom-1", size="10G")
        chain.task.cancel.assert_called_once()
        chain.task.enqueue.assert_not_called()
