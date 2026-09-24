# SPDX-License-Identifier: AGPL-3.0-or-later

"""The recreate chain repoints the desktop before it destroys the disk it replaces.

The chain hung the repoint straight off the create, so the handler that wires the
replacement in ran while the new row was still in its born status and returned
without writing -- the desktop kept naming a disk the same chain then deleted, and
a reconcile pass finalised it Failed while the replacement sat ready and unused.
The order here is the one the create chain already uses: observe the disk, write
its status, repoint, and only then destroy what it replaced.

Two more corrections ride along, and they are not separable. The drop of the old
row asked for it before the status that authorises the drop was written, so it
silently did nothing and the row stayed for ever; and the old row was marked gone
on every outcome, including a chain that never ran the delete and left the file
on disk.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from isardvdi_common.models import storage as mod
from isardvdi_common.models.storage import Storage


def _walk(dep_list, parent_task=None):
    """Yield ``(parent_task, dep)`` for every node of the chain."""
    for dep in dep_list or []:
        yield (parent_task, dep)
        for nested in _walk(dep.get("dependents"), dep.get("task")):
            yield nested


def _ancestors(dep_list, task_name):
    """Task names on the path from the root down to ``task_name``, exclusive."""

    def walk(deps, trail):
        for dep in deps or []:
            if dep.get("task") == task_name:
                return trail
            found = walk(dep.get("dependents"), trail + [dep.get("task")])
            if found is not None:
                return found
        return None

    return walk(dep_list, [])


@pytest.fixture
def chain(monkeypatch):
    """Run ``recreate`` far enough to capture the chain it hands to create_task."""
    captured = {}

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
            "status_logs": [],
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
    monkeypatch.setattr(Storage, "set_maintenance", lambda self, *a, **k: None)
    monkeypatch.setattr(mod.qcow2_geometry, "policy", staticmethod(lambda: {}))
    monkeypatch.setattr(
        mod.StoragePool,
        "get_best_for_action",
        staticmethod(lambda *a, **k: MagicMock(id="pool-1")),
    )
    monkeypatch.setattr(
        mod, "new_storage_directory_path", staticmethod(lambda *a, **k: "/isard/groups")
    )
    monkeypatch.setattr(mod.queue_coverage, "check_shed", lambda *a, **k: None)

    single_disk = MagicMock()
    single_disk.create_dict = {"hardware": {"disks": [{"storage_id": "old-1"}]}}
    fake_domain = MagicMock()
    fake_domain.exists.return_value = True
    fake_domain.return_value = single_disk
    monkeypatch.setattr(mod.domain, "Domain", fake_domain)

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

    def _create_task(self, *a, **k):
        captured.update(k)
        return "task-1"

    monkeypatch.setattr(Storage, "create_task", _create_task)
    old.recreate("u-1", "dom-1")
    return SimpleNamespace(deps=captured["dependents"], kwargs=captured)


def _node(deps, task_name):
    for _parent, dep in _walk(deps):
        if dep.get("task") == task_name:
            return dep
    return None


def _parent_of(deps, task_name):
    for parent, dep in _walk(deps):
        if dep.get("task") == task_name:
            return parent
    return None


class TestTheRepointWaitsForTheStatus:
    def test_the_repoint_is_a_descendant_of_storage_update(self, chain):
        assert "storage_update" in _ancestors(chain.deps, "domain_change_storage")

    def test_the_chain_is_one_spine(self, chain):
        spine = []
        node = _node(chain.deps, "qemu_img_info_backing_chain")
        while node:
            spine.append(node["task"])
            children = node.get("dependents") or []
            assert len(children) <= 1, f"{node['task']} branches"
            node = children[0] if children else None
        assert spine == [
            "qemu_img_info_backing_chain",
            "storage_update",
            "domain_change_storage",
            "delete",
            "update_status",
            "storage_delete",
        ]

    def test_the_old_disk_delete_waits_for_the_repoint(self, chain):
        delete = _node(chain.deps, "delete")
        assert delete["job_kwargs"]["kwargs"]["path"] == "/isard/groups/old-1.qcow2"
        assert _parent_of(chain.deps, "delete") == "domain_change_storage"


class TestTheOldRowIsRetiredOnlyWhenItReallyWent:
    def _terminal(self, chain):
        for parent, dep in _walk(chain.deps):
            if dep.get("task") == "update_status" and parent == "delete":
                return dep["job_kwargs"]["kwargs"]["statuses"]
        raise AssertionError("no update_status under the delete")

    def test_marked_deleted_only_on_a_finished_delete(self, chain):
        statuses = self._terminal(chain)
        assert "_all" not in statuses
        assert statuses["finished"] == {"deleted": {"storage": ["old-1"]}}

    def test_a_failed_delete_puts_the_old_row_back(self, chain):
        statuses = self._terminal(chain)
        assert statuses["failed"] == {"ready": {"storage": ["old-1"]}}
        assert statuses["canceled"] == {"ready": {"storage": ["old-1"]}}

    def test_the_row_is_dropped_after_it_is_marked_deleted(self, chain):
        assert _parent_of(chain.deps, "storage_delete") == "update_status"


class TestADeadCreateReleasesTheDesktop:
    def test_the_root_carries_a_release_branch(self, chain):
        release = chain.deps[0]
        assert release["task"] == "update_status"
        statuses = release["job_kwargs"]["kwargs"]["statuses"]
        for outcome in ("failed", "canceled"):
            assert statuses[outcome]["ready"] == {"storage": ["old-1"]}
            assert statuses[outcome]["Stopped"] == {"domain": ["dom-1"]}
            assert statuses[outcome]["non_existing"] == {"storage": ["new-1"]}
