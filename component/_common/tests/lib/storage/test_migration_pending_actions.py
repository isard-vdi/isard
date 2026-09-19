# SPDX-License-Identifier: AGPL-3.0-or-later

"""The migration leaves a pending-action mark on a disk it found something on."""

from isardvdi_common.lib.storage import migration_run as mr


class _Task:
    results = {}

    def __init__(self, task_id):
        self._id = task_id

    @property
    def result(self):
        value = _Task.results[self._id]
        if isinstance(value, Exception):
            raise value
        return value


def _runner(monkeypatch):
    r = object.__new__(mr.MigrationRunner)
    r.migration_id = "m1"
    r.config = {}
    r._set = lambda item, **f: item.update(f)
    flags = []
    monkeypatch.setattr(mr, "Task", _Task)
    monkeypatch.setattr(
        mr.Storage,
        "flag_pending",
        classmethod(
            lambda cls, sid, action, found_by, detail=None: flags.append(
                (sid, action, found_by, detail)
            )
        ),
    )
    return r, flags


def _item(**extra):
    it = {
        "id": "i1",
        "storage_id": "s1",
        "kind": "desktop",
        "verify_task_id": "v1",
        "state": "rebased",
    }
    it.update(extra)
    return it


def test_a_gate_that_passed_with_leaks_flags_repair_leaks(monkeypatch):
    r, flags = _runner(monkeypatch)
    _Task.results = {"v1": {"leaks": 593, "summary": "leaks=593"}}
    item = _item()

    r._mark_verified(item)

    assert item["verify_passed"] is True
    assert flags == [("s1", "repair_leaks", "migration:m1", {"leaks": 593})]


def test_a_clean_gate_flags_nothing(monkeypatch):
    r, flags = _runner(monkeypatch)
    _Task.results = {"v1": {"leaks": 0, "summary": "no errors"}}
    r._mark_verified(_item())
    assert flags == []


def test_a_media_is_never_flagged(monkeypatch):
    r, flags = _runner(monkeypatch)
    _Task.results = {"v1": {"leaks": 3, "summary": "leaks=3"}}
    r._mark_verified(_item(kind="media"))
    assert flags == []


def test_an_expired_result_costs_only_the_mark(monkeypatch):
    """The rq result may be gone by the time the pass is recorded: the pass
    still stands, the mark is simply not made."""
    r, flags = _runner(monkeypatch)
    _Task.results = {"v1": KeyError("gone")}
    item = _item()
    r._mark_verified(item)
    assert item["verify_passed"] is True and flags == []


def test_a_damaged_disk_is_flagged_for_review(monkeypatch):
    r, flags = _runner(monkeypatch)
    monkeypatch.setattr(
        mr.Storage, "update_document", classmethod(lambda cls, *a, **k: None)
    )
    item = _item()

    r._mark_damaged(item, "/p/s1.qcow2: corruptions=62")

    assert item["damaged"] is True
    assert flags == [
        (
            "s1",
            "review_damage",
            "migration:m1",
            {"reason": "/p/s1.qcow2: corruptions=62"},
        )
    ]
