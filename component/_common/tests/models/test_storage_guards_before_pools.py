# SPDX-License-Identifier: AGPL-3.0-or-later

"""A disk's own refusals come before anything that resolves a pool or a lane."""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models import storage as mod
from isardvdi_common.models.storage import Storage
from isardvdi_common.models.storage_pool import StoragePool


class _PoolResolved(Exception):
    """Raised by the stubbed pool lookup: reaching it means the guard ran late."""


@pytest.fixture
def disk(monkeypatch):
    """A ready, unused disk whose collaborators record what was reached."""
    reached = []
    row = {
        "id": "s-1",
        "status": "ready",
        "parent": None,
        "path": "/isard/groups/s-1.qcow2",
        "directory_path": "/isard/groups",
        "user_id": "u-1",
        "type": "qcow2",
    }
    storage = Storage.__new__(Storage)
    storage.__dict__.update(row)

    monkeypatch.setattr(
        Storage,
        "__setattr__",
        lambda self, name, value: self.__dict__.__setitem__(name, value),
    )
    monkeypatch.setattr(Storage, "get", staticmethod(lambda _id: dict(row)))
    monkeypatch.setattr(Storage, "domains", [])
    monkeypatch.setattr(Storage, "children", [])
    monkeypatch.setattr(Storage, "category", "cat-1")
    monkeypatch.setattr(Storage, "pool", SimpleNamespace(id="default"))

    def _best(action, path=None):
        reached.append(("pool", action))
        return SimpleNamespace(id="default")

    monkeypatch.setattr(StoragePool, "get_best_for_action", staticmethod(_best))
    monkeypatch.setattr(mod.qcow2_geometry, "policy", lambda: {})
    monkeypatch.setattr(mod, "storage_min_free_bytes", lambda: 0)
    monkeypatch.setattr(mod.queue_coverage, "check_shed", lambda conn, q: None)
    monkeypatch.setattr(mod.Task, "_redis", MagicMock(), raising=False)
    monkeypatch.setattr(
        Storage,
        "set_maintenance",
        lambda self, action, *a, **k: reached.append(("maintenance", action)),
    )

    def _create_task(self, **kwargs):
        reached.append(("task", kwargs.get("task")))
        return "task-1"

    monkeypatch.setattr(Storage, "create_task", _create_task)
    storage.reached = reached
    return storage


def _refused(call):
    with pytest.raises(Error) as exc:
        call()
    return exc.value


class TestDisconnectWithoutParent:
    def test_is_refused_before_anything_is_queued(self, disk):
        err = _refused(lambda: disk.disconnect_chain("u-admin"))
        assert err.status_code == 428
        assert err.error["description_code"] == "storage_has_no_parent"
        assert disk.reached == []

    def test_a_derived_disk_still_disconnects(self, disk):
        disk.parent = "base-1"
        assert disk.disconnect_chain("u-admin") == "task-1"
        assert ("task", "disconnect") in disk.reached

    def test_children_are_refused_before_the_pool_is_resolved(self, disk, monkeypatch):
        disk.parent = "base-1"
        monkeypatch.setattr(Storage, "children", ["child-1"])
        err = _refused(lambda: disk.disconnect_chain("u-admin"))
        assert err.error["description_code"] == "storage_has_children"
        assert disk.reached == []


class TestRsyncGuardsFirst:
    def test_a_base_with_children_is_refused_before_the_pool(self, disk, monkeypatch):
        monkeypatch.setattr(Storage, "children", ["child-1"])

        def _unresolvable(action, path=None):
            raise _PoolResolved(action)

        monkeypatch.setattr(
            StoragePool, "get_best_for_action", staticmethod(_unresolvable)
        )
        err = _refused(lambda: disk.rsync("u-admin", "/isard/storage_pools/p2/s-1"))
        assert err.status_code == 428
        assert err.error["description_code"] == "storage_has_children"

    def test_a_lane_without_worker_refuses_before_maintenance(self, disk, monkeypatch):
        def _no_consumer(conn, queue):
            raise Error(
                "too_many_requests",
                "no worker",
                description_code="storage_no_consumer_retry_later",
            )

        monkeypatch.setattr(mod.queue_coverage, "check_shed", _no_consumer)
        err = _refused(lambda: disk.rsync("u-admin", "/isard/storage_pools/p2/s-1"))
        assert err.status_code == 429
        assert err.error["description_code"] == "storage_no_consumer_retry_later"
        assert ("maintenance", "move") not in disk.reached
        assert not any(kind == "task" for kind, _ in disk.reached)

    def test_a_movable_disk_is_queued(self, disk):
        assert disk.rsync("u-admin", "/isard/storage_pools/p2/s-1") == "task-1"
        assert disk.reached[-2:] == [("maintenance", "move"), ("task", "move")]


class TestPoolWithoutPaths:
    def test_a_new_pool_without_paths_is_a_400(self):
        pool = StoragePool.__new__(StoragePool)
        pool.__dict__.update({"id": "p2", "paths": None})
        err = _refused(lambda: pool.get_usage_path("template"))
        assert err.status_code == 400
        assert err.error["description_code"] == "storage_pool_usage_without_path"
