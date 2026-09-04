# SPDX-License-Identifier: AGPL-3.0-or-later

"""``desktops_start`` writes only while each row still holds the status its read loop saw."""

from unittest.mock import MagicMock

import pytest


class _Val:
    def __init__(self, value):
        self.value = value

    def eq(self, other):
        return self.value == other

    def __eq__(self, other):
        return self.value == other

    def __hash__(self):
        return hash(self.value)


class _RowProxy:
    def __init__(self, document):
        self._document = document

    def __getitem__(self, key):
        return _Val(self._document.get(key))


class _Doc:
    def __init__(self, store, doc_id):
        self._store = store
        self._id = doc_id

    def update(self, payload):
        if callable(payload):
            payload = payload(_RowProxy(self._store.get(self._id, {})))
        if payload:
            self._store.setdefault(self._id, {}).update(payload)
        return MagicMock(name="write")


class _Table:
    def __init__(self, fake):
        self._fake = fake

    def get(self, doc_id):
        return _Doc(self._fake.store, doc_id)

    def get_all(self, *_keys, **_kwargs):
        return self

    def filter(self, _predicate):
        return self

    def pluck(self, *_fields):
        return self

    def run(self, _connection):
        return list(self._fake.read_result)


class _FakeR:
    """Enough ReQL to run the write and ignore the read's server-side filter."""

    def __init__(self, store, read_result):
        self.store = store
        self.read_result = read_result
        self.row = _RowProxy({})

    def table(self, _name):
        return _Table(self)

    @staticmethod
    def branch(condition, on_true, on_false):
        return on_true if condition else on_false


@pytest.fixture
def events(monkeypatch):
    from isardvdi_common.helpers import desktop_events as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

    monkeypatch.setattr(
        mod.DesktopEvents, "_rdb_context", classmethod(lambda cls: _Ctx())
    )
    monkeypatch.setattr(
        type(mod.DesktopEvents),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )
    monkeypatch.setattr(mod, "notify_admins", lambda *a, **k: None)
    monkeypatch.setattr(mod.DesktopEvents, "get_qos_disks", classmethod(lambda cls: []))
    monkeypatch.setattr(
        mod.Caches, "get_document", classmethod(lambda cls, *a, **k: "user")
    )

    def _run(read_result, store):
        monkeypatch.setattr(mod, "r", _FakeR(store, read_result))
        mod.DesktopEvents.desktops_start(
            [row["id"] for row in read_result], batch_size=15, wait_seconds=0
        )

    return _run


def _read_row(status):
    return {
        "id": "d1",
        "status": status,
        "user": "u1",
        "create_dict": {"hardware": {}},
    }


def test_a_batch_start_does_not_overwrite_a_failed_written_while_it_read(events):
    """The settle path failed the disk after the read loop passed this row."""
    store = {"d1": {"id": "d1", "status": "Failed"}}

    events([_read_row("Stopped")], store)

    assert store["d1"]["status"] == "Failed", (
        "the batch start overwrote a Failed the settle path had just written: "
        f"{store['d1']}"
    )


def test_a_batch_start_does_not_restart_a_desktop_that_started_meanwhile(events):
    """A row that left the readable set entirely must be skipped too."""
    store = {"d1": {"id": "d1", "status": "Started"}}

    events([_read_row("Stopped")], store)

    assert store["d1"]["status"] == "Started", f"a live desktop was restarted: {store}"


def test_a_batch_start_still_starts_a_desktop_that_has_not_moved(events):
    """The control: the ordinary path must keep working."""
    store = {"d1": {"id": "d1", "status": "Stopped"}}

    events([_read_row("Stopped")], store)

    assert store["d1"]["status"] == "Starting"
    assert store["d1"]["viewer"] == {}


def test_a_batch_start_still_starts_a_desktop_that_was_read_failed(events):
    """Starting a Failed desktop is the point of the Failed half of the filter."""
    store = {"d1": {"id": "d1", "status": "Failed"}}

    events([_read_row("Failed")], store)

    assert store["d1"]["status"] == "Starting"
