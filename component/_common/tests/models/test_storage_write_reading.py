#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``Storage.write_reading`` decides inside the write whether a reading may
set the status, so a row sent to the recycle bin after the task read the disk
stays ``recycled``. ``r`` is replaced with a tiny evaluator that applies the
update to an in-memory row, the way the server would."""

from contextlib import nullcontext

import pytest


class _Bool:
    def __init__(self, value):
        self._value = bool(value)

    def __bool__(self):
        return self._value

    def or_(self, other):
        return _Bool(self._value or bool(other))

    def and_(self, other):
        return _Bool(self._value and bool(other))


class _Value:
    def __init__(self, value):
        self._value = value

    def default(self, fallback):
        return _Value(fallback if self._value is None else self._value)

    def eq(self, other):
        return _Bool(self._value == other)

    def gt(self, other):
        return _Bool(self._value > other)


class _Row:
    def __init__(self, doc):
        self._doc = doc

    def __getitem__(self, field):
        return _Value(self._doc.get(field))


class _Expr(dict):
    def without(self, *fields):
        return {k: v for k, v in self.items() if k not in fields}


class _List(list):
    def contains(self, value):
        return _Bool(value._value in self)


class _Get:
    def __init__(self, store, doc_id):
        self.store, self.doc_id = store, doc_id

    def update(self, change, return_changes=False):
        self.change = change
        return self

    def run(self, _conn):
        doc = self.store.get(self.doc_id)
        if doc is None:
            return {"skipped": 1, "changes": []}
        patch = self.change(_Row(doc)) if callable(self.change) else self.change
        new = {**doc, **patch}
        self.store[self.doc_id] = new
        return {"replaced": int(new != doc), "changes": [{"new_val": new}]}


class _R:
    def __init__(self, store):
        self.store = store

    def table(self, _name):
        store = self.store
        return type("T", (), {"get": lambda _s, doc_id: _Get(store, doc_id)})()

    @staticmethod
    def branch(condition, when_true, when_false):
        return when_true if condition else when_false

    @staticmethod
    def expr(value):
        return _List(value) if isinstance(value, list) else _Expr(value)


@pytest.fixture
def store(monkeypatch):
    from isardvdi_common.models import storage as mod

    rows = {}
    monkeypatch.setattr(mod, "r", _R(rows))
    monkeypatch.setattr(
        mod.Storage, "_rdb_context", classmethod(lambda cls: nullcontext())
    )
    return mod.Storage, rows


def test_a_ready_reading_keeps_a_recycled_row_recycled(store):
    Storage, rows = store
    rows["s1"] = {"id": "s1", "status": "recycled", "status_time": 1}
    status = Storage.write_reading(
        {"id": "s1", "status": "ready", "qemu-img-info": {"actual-size": 7}}
    )
    assert status == "recycled"
    assert rows["s1"]["status"] == "recycled"
    assert rows["s1"]["status_time"] == 1
    assert rows["s1"]["qemu-img-info"] == {"actual-size": 7}


@pytest.mark.parametrize("current", ["maintenance", "ready", None])
def test_a_ready_reading_sets_ready_on_any_other_row(store, current):
    Storage, rows = store
    rows["s1"] = {"id": "s1", "status": current, "status_time": 1}
    assert Storage.write_reading({"id": "s1", "status": "ready"}) == "ready"
    assert rows["s1"]["status"] == "ready"
    assert rows["s1"]["status_time"] > 1


@pytest.mark.parametrize("reading", ["broken_chain", "orphan", "deleted"])
def test_no_reading_moves_a_recycled_row(store, reading):
    Storage, rows = store
    rows["s1"] = {"id": "s1", "status": "recycled"}
    assert Storage.write_reading({"id": "s1", "status": reading}) == "recycled"


def test_an_observer_leaves_a_row_in_maintenance_to_its_chain(store):
    Storage, rows = store
    rows["s1"] = {"id": "s1", "status": "maintenance", "status_time": 1}
    status = Storage.write_reading(
        {"id": "s1", "status": "ready", "qemu-img-info": {"actual-size": 7}},
        observer=True,
    )
    assert status == "maintenance"
    assert rows["s1"]["status_time"] == 1
    assert rows["s1"]["qemu-img-info"] == {"actual-size": 7}


def test_the_chain_that_holds_maintenance_releases_it(store):
    Storage, rows = store
    rows["s1"] = {"id": "s1", "status": "maintenance", "status_time": 1}
    assert Storage.write_reading({"id": "s1", "status": "ready"}) == "ready"


def test_a_row_deleted_after_the_reading_started_stays_deleted(store):
    Storage, rows = store
    rows["s1"] = {"id": "s1", "status": "deleted", "status_time": 200}
    assert Storage.write_reading({"id": "s1", "status": "ready"}, read_at=100) == (
        "deleted"
    )


def test_a_reading_started_after_the_deletion_recovers_the_row(store):
    Storage, rows = store
    rows["s1"] = {"id": "s1", "status": "deleted", "status_time": 100}
    assert Storage.write_reading({"id": "s1", "status": "ready"}, read_at=200) == (
        "ready"
    )


@pytest.mark.parametrize(
    "current, written, expected",
    [
        ("recycled", "ready", "recycled"),
        ("recycled", "maintenance", "recycled"),
        ("deleted", "ready", "deleted"),
        ("recycled", "deleted", "deleted"),
        ("maintenance", "ready", "ready"),
        ("ready", "deleted", "deleted"),
    ],
)
def test_write_status_never_brings_a_row_out_of_the_bin(
    store, current, written, expected
):
    Storage, rows = store
    rows["s1"] = {"id": "s1", "status": current}
    assert Storage.write_status("s1", written) == expected
    assert rows["s1"]["status"] == expected


def test_write_status_for_a_row_that_is_gone_writes_nothing(store):
    Storage, rows = store
    assert Storage.write_status("s1", "ready") is None
    assert rows == {}


def test_a_reading_for_a_row_that_is_gone_writes_nothing(store):
    Storage, rows = store
    assert Storage.write_reading({"id": "s1", "status": "ready"}) is None
    assert rows == {}
