# SPDX-License-Identifier: AGPL-3.0-or-later

"""``clear_pending(found_by=...)`` drops only the mark that finder left."""

from contextlib import nullcontext

import pytest


class _Row:
    def __init__(self, value):
        self._value = value

    def __getitem__(self, field):
        return _Row(self._value.get(field) if isinstance(self._value, dict) else None)

    def __eq__(self, other):
        return self._value == other

    def default(self, fallback):
        return _Row(fallback if self._value is None else self._value)

    def without(self, spec):
        doc = dict(self._value)
        for key, inner in spec.items():
            if inner is True:
                doc.pop(key, None)
            else:
                doc[key] = _Row(doc.get(key) or {}).without(inner)
        return doc


class _Get:
    def __init__(self, store, doc_id):
        self.store, self.doc_id = store, doc_id

    def replace(self, change):
        self.change = change
        return self

    def run(self, _conn):
        new = self.change(_Row(self.store[self.doc_id]))
        self.store[self.doc_id] = new._value if isinstance(new, _Row) else new


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


def _row(found_by):
    return {
        "id": "s1",
        "pending_actions": {
            "review_coherence": {"found_by": found_by},
            "sparsify": {"found_by": "x"},
        },
    }


def test_the_finder_s_own_mark_is_dropped(store):
    Storage, rows = store
    rows["s1"] = _row("check_integrity")
    Storage.clear_pending("s1", "review_coherence", found_by="check_integrity")
    assert rows["s1"]["pending_actions"] == {"sparsify": {"found_by": "x"}}


def test_another_finder_s_mark_is_kept(store):
    Storage, rows = store
    rows["s1"] = _row("the integrity coherence pass")
    Storage.clear_pending("s1", "review_coherence", found_by="check_integrity")
    assert rows["s1"] == _row("the integrity coherence pass")


def test_without_found_by_any_mark_is_dropped(store):
    Storage, rows = store
    rows["s1"] = _row("the integrity coherence pass")
    Storage.clear_pending("s1", "review_coherence")
    assert "review_coherence" not in rows["s1"]["pending_actions"]
