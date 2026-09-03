"""The domains changes thread survives the database being recreated.

`run()` used to call `r.connect()`, build the `.changes()` cursor and iterate it
with no statement-level `try` — the only one is inside the loop body and cannot
catch what the cursor raises on the way out. When the database went away the
exception left `run()`, the thread ended for the lifetime of the container, and
nothing rearmed it: every desktop action reacts to that cursor, so desktops sat
in transition for ever with nothing logged as broken.

These bypass `__init__` (it builds a thread pool) and stub the two collaborators
the loop touches.
"""

import sys
import threading
from itertools import count
from unittest.mock import MagicMock

# The shared bootstrap stubs ``rethinkdb`` as a MagicMock, and no other test
# under engine/models imports engine.models.engine — which reaches isardvdi_common's
# shared connection and from-imports three rethinkdb submodules a MagicMock cannot
# satisfy. Stub them HERE: putting them in the shared conftest breaks the separate
# importlib-mode invocation over engine/services/db.
for _mod in (
    "rethinkdb.connection_pool",
    "rethinkdb.errors",
    "rethinkdb.net",
    "isardvdi_common.connections.rethink_connection_factory",
    "isardvdi_common.connections.rethink_shared_connection",
):
    sys.modules.setdefault(_mod, MagicMock())

from engine.models.engine import Engine  # noqa: E402


def _thread(monkeypatch, consume, sleeps):
    t = Engine.DomainsChangesThread.__new__(Engine.DomainsChangesThread)
    threading.Thread.__init__(t, name="changes_domains")
    t.stop = False
    t.r_conn = False
    t.manager = None
    t.executor = type("E", (), {"shutdown": lambda self, wait=False: None})()
    t._consume_changes = lambda ui: consume(t)
    monkeypatch.setattr("engine.models.engine.get_tid", lambda: 1)
    monkeypatch.setattr("engine.models.engine.UiActions", lambda manager: object())
    monkeypatch.setattr("engine.models.engine.sleep", sleeps.append)
    return t


def test_a_dead_cursor_reconnects_instead_of_ending_the_thread(monkeypatch):
    calls = []
    sleeps = []

    def consume(t):
        calls.append(1)
        if len(calls) == 3:
            t.stop = True
            return
        raise Exception("Connection is closed")

    _thread(monkeypatch, consume, sleeps).run()

    assert len(calls) == 3  # it came back twice instead of dying on the first
    assert sleeps == [5, 10]  # and backed off between attempts


def test_a_cursor_that_lived_resets_the_backoff(monkeypatch):
    """Otherwise the delay ratchets to its cap for the life of the container:
    a box that has seen a few database restarts then waits a full minute before
    even trying to reconnect, and every desktop action in that window is lost."""
    sleeps = []
    # every reading is 500s past the previous one, so each cursor "lived"
    clock = count(0, 500)
    monkeypatch.setattr("engine.models.engine.monotonic", lambda: next(clock))

    def consume(t):
        if len(sleeps) >= 3:
            t.stop = True
            return
        raise Exception("db bounced")

    _thread(monkeypatch, consume, sleeps).run()

    # each cursor lived well past CURSOR_HEALTHY_SECONDS, so no doubling carries
    assert sleeps == [5, 5, 5]


def test_a_cursor_that_dies_at_once_keeps_backing_off(monkeypatch):
    """The floor is only for connections that worked: a database that is not
    coming back must not be hammered every 5s."""
    sleeps = []
    clock = count(0, 1)  # every cursor dies within a second of opening
    monkeypatch.setattr("engine.models.engine.monotonic", lambda: next(clock))

    def consume(t):
        if len(sleeps) >= 3:
            t.stop = True
            return
        raise Exception("still down")

    _thread(monkeypatch, consume, sleeps).run()

    assert sleeps == [5, 10, 20]


def test_the_backoff_is_capped(monkeypatch):
    sleeps = []

    def consume(t):
        if len(sleeps) >= 8:
            t.stop = True
            return
        raise Exception("nope")

    _thread(monkeypatch, consume, sleeps).run()

    assert max(sleeps) == 60


def test_the_old_connection_is_closed_before_reconnecting(monkeypatch):
    closed = []

    class _Conn:
        def close(self, noreply_wait=True):
            closed.append(noreply_wait)

    def consume(t):
        t.r_conn = _Conn()
        if closed:
            t.stop = True
            return
        raise Exception("Connection is closed")

    t = _thread(monkeypatch, consume, [])
    t.run()

    # closed on every exit, and never left behind for the next attempt to leak
    assert closed == [False, False]
    assert t.r_conn is False


def test_a_dead_socket_that_refuses_to_close_does_not_kill_the_thread(monkeypatch):
    class _Conn:
        def close(self, noreply_wait=True):
            raise OSError("socket already gone")

    def consume(t):
        t.r_conn = _Conn()
        t.stop = True

    _thread(monkeypatch, consume, []).run()  # must not raise


def test_a_stop_request_ends_the_loop_without_sleeping(monkeypatch):
    sleeps = []

    def consume(t):
        t.stop = True

    _thread(monkeypatch, consume, sleeps).run()

    assert sleeps == []
