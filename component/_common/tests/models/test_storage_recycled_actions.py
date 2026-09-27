#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""A disk in the recycle bin takes no action, and a check only releases
``maintenance`` when it is asked to heal a row whose own chain is gone."""

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models import storage as mod


def _storage(monkeypatch, status):
    obj = object.__new__(mod.Storage)
    obj.__dict__.update(
        {
            "id": "s1",
            "status": status,
            "directory_path": "/isard/groups/x",
            "type": "qcow2",
        }
    )
    calls = []
    monkeypatch.setattr(
        mod.Storage, "create_task", lambda self, *a, **k: calls.append(k) or "t1"
    )
    monkeypatch.setattr(
        mod.StoragePool,
        "get_best_for_action",
        classmethod(lambda cls, *a, **k: type("P", (), {"id": "p"})()),
    )
    monkeypatch.setattr(
        mod.Storage, "set_maintenance", lambda self, *a, **k: calls.append("maint")
    )
    monkeypatch.setattr(mod.Storage, "domains", property(lambda self: []))
    monkeypatch.setattr(mod.Storage, "domains_derivatives", property(lambda self: []))
    return obj, calls


@pytest.mark.parametrize(
    "action",
    [
        lambda s: s.find("u"),
        lambda s: s.check_backing_chain("u"),
        lambda s: s.task_delete("u"),
    ],
    ids=["find", "check_backing_chain", "task_delete"],
)
def test_no_action_is_enqueued_on_a_recycled_disk(monkeypatch, action):
    storage, calls = _storage(monkeypatch, "recycled")
    with pytest.raises(Error) as refused:
        action(storage)
    assert refused.value.error["description_code"] == "storage_recycled"
    assert calls == []


def test_a_check_only_observes(monkeypatch):
    storage, calls = _storage(monkeypatch, "maintenance")
    storage.check_backing_chain("u")
    assert calls[0]["dependents"] == [
        {
            "queue": "core",
            "task": "storage_update",
            "job_kwargs": {"kwargs": {"observer": True}},
        }
    ]


def test_a_healing_check_may_release_maintenance(monkeypatch):
    storage, calls = _storage(monkeypatch, "maintenance")
    storage.check_backing_chain("u", release_maintenance=True)
    assert calls[0]["dependents"] == [{"queue": "core", "task": "storage_update"}]
