"""``update_domain_status`` writes a status the caller decided from a stale read."""

import importlib.util as _ilu
import sys as _sys
import types as _types
from unittest.mock import MagicMock as _MagicMock

from tests.helpers import ENGINE_SRC

# set the level on the existing ``logs``: replacing the module breaks sibling tests
import engine.services.log as _engine_log

try:
    _engine_log.logs.changes.handlers[0].level = 20
except Exception:
    pass

# load from file under a stub package so db/__init__ and its connections never run
_saved = {
    _m: _sys.modules.get(_m)
    for _m in (
        "engine.services.db",
        "engine.services.db.db",
        "engine.services.db.domains",
        "rethinkdb",
    )
}
_pkg = _types.ModuleType("engine.services.db")
_pkg.__path__ = []
for _name in (
    "close_rethink_connection",
    "create_list_buffer_history_domain",
    "new_rethink_connection",
    "rethink_conn",
):
    setattr(_pkg, _name, _MagicMock())
_sys.modules["engine.services.db"] = _pkg
# domains.py also imports engine.services.db.db, which connects at import time.
_db = _types.ModuleType("engine.services.db.db")
_db.close_rethink_connection = _MagicMock()
_db.new_rethink_connection = _MagicMock()
_sys.modules["engine.services.db.db"] = _db
_sys.modules.pop("rethinkdb", None)

_spec = _ilu.spec_from_file_location(
    "engine.services.db.domains",
    str(ENGINE_SRC / "services" / "db" / "domains.py"),
)
mod = _ilu.module_from_spec(_spec)
_sys.modules[_spec.name] = mod
_spec.loader.exec_module(mod)

for _m, _prev in _saved.items():
    if _prev is None:
        _sys.modules.pop(_m, None)
    else:
        _sys.modules[_m] = _prev

from contextlib import contextmanager  # noqa: E402
from unittest.mock import patch  # noqa: E402

import pytest  # noqa: E402

REQL_NULL_ERROR = object()


class _Val:
    def __init__(self, value):
        self.value = value

    def eq(self, other):
        # Comparing a field read off a null row is itself a server error, not
        # a false: the error has to propagate to whatever branch consumes it.
        if self.value is REQL_NULL_ERROR:
            return REQL_NULL_ERROR
        return self.value == other


class _PoisonedRow:
    """Result of operating on a null row, which the server rejects with errors: 1."""

    document = REQL_NULL_ERROR

    def __getitem__(self, _key):
        return _Val(REQL_NULL_ERROR)

    def without(self, *_fields):
        return self

    def merge(self, _other):
        return self


class _MissingRow:
    """What ``get`` hands the lambda when the row is gone: a null, not a {}."""

    document = None

    def eq(self, other):
        return other is None

    def __getitem__(self, _key):
        return _Val(REQL_NULL_ERROR)

    def without(self, *_fields):
        return _PoisonedRow()

    def merge(self, _other):
        return _PoisonedRow()


class _RowProxy:
    def __init__(self, document):
        self.document = document

    def eq(self, other):
        return self.document == other

    def __getitem__(self, key):
        return _Val(self.document.get(key))

    def without(self, *fields):
        dropped = {f for f in fields if isinstance(f, str)}
        return _RowProxy({k: v for k, v in self.document.items() if k not in dropped})

    def merge(self, other):
        return _RowProxy({**self.document, **other})


class _Doc:
    def __init__(self, store, doc_id):
        self.store = store
        self.doc_id = doc_id

    def _row(self):
        if self.doc_id not in self.store:
            return _MissingRow()
        return _RowProxy(self.store[self.doc_id])

    def update(self, payload, return_changes=False):
        if callable(payload):
            payload = payload(self._row())
        if not payload:
            return {"replaced": 0, "unchanged": 0, "skipped": 1}
        self.store.setdefault(self.doc_id, {}).update(payload)
        return {"replaced": 1, "unchanged": 0, "skipped": 0}

    def replace(self, payload, return_changes=False):
        before = self.store.get(self.doc_id)
        after = payload(self._row()).document
        if after is REQL_NULL_ERROR:
            return {
                "replaced": 0,
                "unchanged": 0,
                "skipped": 0,
                "errors": 1,
                "first_error": (
                    "Cannot perform without on a non-object non-sequence `null`."
                ),
            }
        if after is None:
            return {"replaced": 0, "unchanged": 0, "skipped": 1, "errors": 0}
        self.store[self.doc_id] = after
        return {"replaced": 0 if after == before else 1, "unchanged": 0, "skipped": 0}

    def pluck(self, *_fields):
        return self

    def run(self, _connection):
        return self.store.get(self.doc_id, {})


class _FakeR:
    def __init__(self, store):
        self.store = store

    def table(self, _name):
        return self

    def get(self, doc_id):
        return _Doc(self.store, doc_id)

    @staticmethod
    def branch(condition, on_true, on_false):
        if condition is REQL_NULL_ERROR:
            return _PoisonedRow()
        return on_true if condition else on_false


@pytest.fixture
def store(monkeypatch):
    rows = {}

    class _Table:
        def __init__(self, doc):
            self.doc = doc

        def update(self, payload, return_changes=False):
            self.result = self.doc.update(payload, return_changes)
            return self

        def replace(self, payload, return_changes=False):
            self.result = self.doc.replace(payload, return_changes)
            return self

        def pluck(self, *fields):
            return self.doc.pluck(*fields)

        def run(self, _connection):
            return self.result

    class _R(_FakeR):
        def get(self, doc_id):
            return _Table(_Doc(self.store, doc_id))

        class ReqlNonExistenceError(Exception):
            pass

    fake = _R(rows)

    @contextmanager
    def _conn():
        yield _MagicMock(name="conn")

    monkeypatch.setattr(mod, "r", fake)
    monkeypatch.setattr(mod, "rethink_conn", _conn)
    monkeypatch.setattr(mod, "remove_fieds_when_stopped", lambda *a, **k: None)
    return rows


def test_the_broom_does_not_stop_a_domain_a_settle_failed_while_it_polled(store):
    """``Failed`` is not transitional, so the snapshot cannot see it."""
    store["d1"] = {"id": "d1", "status": "Failed"}

    mod.update_domain_status("Stopped", "d1", expected_status="Stopping")

    assert (
        store["d1"]["status"] == "Failed"
    ), f"the broom overwrote a Failed the settle path had written: {store['d1']}"


def test_the_broom_does_not_stop_a_domain_that_reached_started_while_it_polled(store):
    """The symmetric loss: a domain that legitimately came up mid-window."""
    store["d1"] = {"id": "d1", "status": "Started", "hyp_started": "hyp1"}

    mod.update_domain_status("Stopped", "d1", expected_status="Shutting-down")

    assert store["d1"]["status"] == "Started"
    assert store["d1"]["hyp_started"] == "hyp1", "the viewer's hypervisor was cleared"


def test_the_broom_does_not_fail_a_domain_that_left_resetting(store):
    """The non-Stopped write path takes the same guard."""
    store["d1"] = {"id": "d1", "status": "Started"}

    mod.update_domain_status("Failed", "d1", expected_status="Resetting")

    assert store["d1"]["status"] == "Started"


def test_the_broom_still_stops_a_domain_that_has_not_moved(store):
    """The control: the ordinary path must keep working."""
    store["d1"] = {"id": "d1", "status": "Stopping", "viewer": {"x": 1}}

    mod.update_domain_status("Stopped", "d1", expected_status="Stopping")

    assert store["d1"]["status"] == "Stopped"
    assert "viewer" not in store["d1"]


def test_the_broom_still_fails_a_domain_that_has_not_moved(store):
    store["d1"] = {"id": "d1", "status": "Resetting"}

    mod.update_domain_status("Failed", "d1", expected_status="Resetting")

    assert store["d1"]["status"] == "Failed"


def test_a_caller_that_names_no_expected_status_still_writes_unconditionally(store):
    """Every other caller passes nothing and must keep its old behaviour."""
    store["d1"] = {"id": "d1", "status": "Started"}

    mod.update_domain_status("Failed", "d1")

    assert store["d1"]["status"] == "Failed"


def test_a_caller_that_names_no_expected_status_still_stops_unconditionally(store):
    store["d1"] = {"id": "d1", "status": "Started", "viewer": {"x": 1}}

    mod.update_domain_status("Stopped", "d1")

    assert store["d1"]["status"] == "Stopped"
    assert "viewer" not in store["d1"]


def test_a_guarded_failed_that_is_skipped_does_not_strip_the_row(store):
    """``remove_fieds_when_stopped`` must not run for a write that never landed."""
    store["d1"] = {"id": "d1", "status": "Started"}
    stripped = []

    with patch.object(mod, "remove_fieds_when_stopped", stripped.append):
        mod.update_domain_status("Failed", "d1", expected_status="Resetting")

    assert stripped == [], "a row the guard protected was stripped anyway"


def test_a_stop_against_a_row_that_is_gone_neither_errors_nor_recreates_it(store):
    """The deleted-row guard must wrap the expected-status one."""
    assert "d1" not in store

    result = mod.update_domain_status("Stopped", "d1")

    assert "d1" not in store, "a write recreated a domain that had been deleted"
    assert not result.get("errors"), result.get("first_error")


def test_a_guarded_stop_against_a_row_that_is_gone_is_also_safe(store):
    assert "d1" not in store

    result = mod.update_domain_status("Stopped", "d1", expected_status="Stopping")

    assert "d1" not in store
    assert not result.get("errors"), result.get("first_error")
