#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``flag_pending(if_absent=True)`` leaves a mark already on the row untouched."""

from contextlib import nullcontext

import pytest


class _Value:
    def __init__(self, value):
        self._value = value

    def __getitem__(self, field):
        return _Value(self._value.get(field) if isinstance(self._value, dict) else None)

    def default(self, fallback):
        return _Value(fallback if self._value is None else self._value)

    def eq(self, other):
        return self._value == other


def _resolve(value):
    if isinstance(value, _Value):
        return value._value
    if isinstance(value, dict):
        return {k: _resolve(v) for k, v in value.items()}
    return value


def _merge(doc, patch):
    merged = dict(doc)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _merge(merged[key], value)
        else:
            merged[key] = value
    return merged


class _Get:
    def __init__(self, store, doc_id):
        self.store, self.doc_id = store, doc_id

    def update(self, change):
        self.change = change
        return self

    def run(self, _conn):
        doc = self.store.get(self.doc_id)
        if doc is None:
            return {"skipped": 1}
        patch = _resolve(self.change(_Value(doc)))
        new = _merge(doc, patch)
        self.store[self.doc_id] = new
        return {"replaced": int(new != doc), "unchanged": int(new == doc)}


class _R:
    def __init__(self, store):
        self.store = store

    def table(self, _name):
        store = self.store
        return type("T", (), {"get": lambda _s, doc_id: _Get(store, doc_id)})()

    @staticmethod
    def branch(condition, when_true, when_false):
        return when_true if condition else when_false


@pytest.fixture
def store(monkeypatch):
    from isardvdi_common.models import storage as mod

    rows = {}
    monkeypatch.setattr(mod, "r", _R(rows))
    monkeypatch.setattr(
        mod.Storage, "_rdb_context", classmethod(lambda cls: nullcontext())
    )
    return mod.Storage, rows


_EXISTING = {
    "since": 1,
    "found_by": "migration verify gate",
    "detail": {"reason": "the copy did not verify"},
    "found_at": 1,
}


def test_if_absent_leaves_an_existing_mark_exactly_as_it_is(store):
    Storage, rows = store
    rows["s1"] = {"id": "s1", "pending_actions": {"review_damage": dict(_EXISTING)}}
    result = Storage.flag_pending(
        "s1", "review_damage", "storage refresh", {"error": "e"}, if_absent=True
    )
    assert rows["s1"]["pending_actions"]["review_damage"] == _EXISTING
    assert result["replaced"] == 0


def test_if_absent_flags_a_row_that_carries_other_marks(store):
    Storage, rows = store
    rows["s1"] = {"id": "s1", "pending_actions": {"sparsify": {"since": 5}}}
    Storage.flag_pending(
        "s1", "review_damage", "storage refresh", {"error": "e"}, if_absent=True
    )
    mark = rows["s1"]["pending_actions"]["review_damage"]
    assert mark["found_by"] == "storage refresh"
    assert mark["detail"] == {"error": "e"}
    assert rows["s1"]["pending_actions"]["sparsify"] == {"since": 5}


def test_if_absent_flags_a_row_with_no_marks_at_all(store):
    Storage, rows = store
    rows["s1"] = {"id": "s1", "status": "ready"}
    Storage.flag_pending("s1", "review_damage", "storage refresh", if_absent=True)
    assert rows["s1"]["pending_actions"]["review_damage"]["since"] > 1


def test_without_if_absent_the_mark_is_refreshed_and_keeps_its_since(store):
    Storage, rows = store
    rows["s1"] = {"id": "s1", "pending_actions": {"review_damage": dict(_EXISTING)}}
    Storage.flag_pending("s1", "review_damage", "storage refresh")
    mark = rows["s1"]["pending_actions"]["review_damage"]
    assert mark["since"] == 1
    assert mark["found_by"] == "storage refresh"


def test_a_row_that_is_gone_is_not_created(store):
    Storage, rows = store
    Storage.flag_pending("s1", "review_damage", "storage refresh", if_absent=True)
    assert rows == {}
