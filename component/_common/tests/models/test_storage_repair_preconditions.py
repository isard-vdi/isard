# SPDX-License-Identifier: AGPL-3.0-or-later

"""``Storage.repair`` admission and the ``repair`` branch of ``set_maintenance``.

A repair is only admitted for a disk that is ``damaged`` or still carries a
``repair_leaks`` mark, and — unlike every other maintenance action — it may lock
a disk whose status is ``damaged`` and whose desktop is ``Failed``. These tests
never touch RethinkDB: instances are built via ``__new__`` and only the
attributes each branch reads are set.
"""

from types import SimpleNamespace

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.models import storage as storage_mod
from isardvdi_common.models.storage import Storage


def _bare(status, domains=(), children=(), pending_actions=None, **extra):
    storage = Storage.__new__(Storage)
    storage.__dict__["id"] = "s-1"
    storage.__dict__["status"] = status
    storage.__dict__["pending_actions"] = pending_actions
    storage.__dict__["_domains"] = list(domains)
    storage.__dict__["_children"] = list(children)
    storage.__dict__.update(extra)
    type(storage).domains = property(lambda self: self.__dict__["_domains"])
    type(storage).children = property(lambda self: self.__dict__["_children"])
    return storage


class _Domain:
    def __init__(self, status="Stopped", domain_id="domain-1"):
        self.id = domain_id
        self.status = status
        self.current_action = None


def _code(excinfo):
    err = excinfo.value
    return getattr(err, "description_code", None) or (
        err.error.get("description_code")
        if isinstance(getattr(err, "error", None), dict)
        else None
    )


# --- Storage.repair admission (checked before set_maintenance) ---------------


def test_repair_rejects_an_unknown_what():
    storage = _bare("damaged")
    with pytest.raises(Error) as excinfo:
        storage.repair("user-1", "everything")
    assert _code(excinfo) == "storage_repair_invalid_what"


def test_repair_refuses_a_healthy_disk_with_nothing_pending():
    storage = _bare("ready", pending_actions=None)
    with pytest.raises(Error) as excinfo:
        storage.repair("user-1", "leaks")
    assert _code(excinfo) == "storage_not_repairable"


def test_repair_refuses_a_ready_disk_whose_only_mark_is_unrelated():
    storage = _bare("ready", pending_actions={"sparsify": {"since": 1}})
    with pytest.raises(Error) as excinfo:
        storage.repair("user-1", "leaks")
    assert _code(excinfo) == "storage_not_repairable"


def _stub_task_creation(monkeypatch, storage):
    """Shadow set_maintenance/create_task on the instance (via __dict__, so the
    persisting __setattr__ is bypassed) and the pool lookup, and capture the
    create_task call."""
    captured = {}
    storage.__dict__["set_maintenance"] = lambda action: captured.setdefault(
        "maintenance", action
    )
    storage.__dict__["create_task"] = lambda **kw: captured.update(kw) or "task-1"
    monkeypatch.setattr(
        storage_mod.StoragePool,
        "get_best_for_action",
        classmethod(lambda cls, action, path=None: SimpleNamespace(id="pool-1")),
    )
    return captured


def test_repair_of_a_damaged_disk_builds_the_two_dependent_chain(monkeypatch):
    storage = _bare("damaged", directory_path="/pool/cat/groups", type="qcow2")
    captured = _stub_task_creation(monkeypatch, storage)

    tid = storage.repair("user-1", "leaks")

    assert tid == "task-1"
    assert captured["maintenance"] == "repair"  # locked before enqueue
    assert captured["task"] == "qemu_img_check_repair"
    assert captured["job_kwargs"]["kwargs"] == {
        "storage_path": storage.path,
        "what": "leaks",
    }
    deps = {d["task"]: d for d in captured["dependents"]}
    # the status authority, a DIRECT dependent, carries the pre-repair status
    assert deps["storage_repair_result"]["job_kwargs"]["kwargs"] == {
        "storage_id": "s-1",
        "previous_status": "damaged",
    }
    # the SIZE re-measure ends in the size-only handler, never storage_update
    remeasure = deps["qemu_img_info_backing_chain"]
    assert remeasure["dependents"][0]["task"] == "storage_repair_size"


def test_repair_is_admitted_for_a_ready_disk_carrying_repair_leaks(monkeypatch):
    storage = _bare(
        "ready",
        pending_actions={"repair_leaks": {"since": 1}},
        directory_path="/pool/cat/groups",
        type="qcow2",
    )
    captured = _stub_task_creation(monkeypatch, storage)

    storage.repair("user-1", "all")

    assert captured["task"] == "qemu_img_check_repair"
    assert (
        captured["dependents"][0]["job_kwargs"]["kwargs"]["previous_status"] == "ready"
    )


# --- set_maintenance("repair") branch ---------------------------------------


def _no_persist(monkeypatch):
    """Make attribute writes stay in memory so the accept path can be asserted
    without a database."""
    monkeypatch.setattr(
        Storage, "__setattr__", lambda self, k, v: self.__dict__.__setitem__(k, v)
    )


def test_set_maintenance_repair_accepts_a_damaged_disk(monkeypatch):
    _no_persist(monkeypatch)
    storage = _bare("damaged", domains=[_Domain("Stopped")])
    storage.set_maintenance("repair")
    assert storage.status == "maintenance"
    assert storage.domains[0].status == "Maintenance"


def test_set_maintenance_repair_accepts_a_failed_domain(monkeypatch):
    _no_persist(monkeypatch)
    storage = _bare("damaged", domains=[_Domain("Failed")])
    storage.set_maintenance("repair")  # must not raise
    assert storage.status == "maintenance"


def test_set_maintenance_repair_rejects_a_started_domain():
    storage = _bare("damaged", domains=[_Domain("Started")])
    with pytest.raises(Error) as excinfo:
        storage.set_maintenance("repair")
    assert _code(excinfo) == "desktops_not_stopped"


def test_set_maintenance_repair_rejects_a_wrong_status():
    storage = _bare("recycled")
    with pytest.raises(Error) as excinfo:
        storage.set_maintenance("repair")
    assert _code(excinfo) == "storage_invalid_status_for_repair"


def test_the_failed_domain_allowance_is_repair_only():
    """Control: a non-repair action still refuses a Failed domain, so the
    allowance can't leak into convert/sparsify/etc."""
    storage = _bare("ready", domains=[_Domain("Failed")])
    with pytest.raises(Error) as excinfo:
        storage.set_maintenance("convert")
    assert _code(excinfo) == "desktops_not_stopped"
