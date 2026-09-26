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


class _Value:
    def __init__(self, value):
        self._value = value

    def default(self, fallback):
        return _Value(fallback if self._value is None else self._value)

    def eq(self, other):
        return self._value == other


class _Row:
    def __init__(self, doc):
        self._doc = doc

    def __getitem__(self, field):
        return _Value(self._doc.get(field))


class _Expr(dict):
    def without(self, *fields):
        return {k: v for k, v in self.items() if k not in fields}


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
        return _Expr(value)


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


def test_a_reading_that_the_file_is_gone_still_applies_to_a_recycled_row(store):
    Storage, rows = store
    rows["s1"] = {"id": "s1", "status": "recycled"}
    assert Storage.write_reading({"id": "s1", "status": "broken_chain"}) == (
        "broken_chain"
    )


def test_a_reading_for_a_row_that_is_gone_writes_nothing(store):
    Storage, rows = store
    assert Storage.write_reading({"id": "s1", "status": "ready"}) is None
    assert rows == {}
