# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the job store that never reconnected.

Driven through the store's ``client=`` seam: ``RqlQuery.run(conn)`` reduces to
``conn._start(term)``, so no server and no gevent loop are needed.
"""

import ast
import time
from datetime import datetime
from pathlib import Path

import pytest
import pytz
from rethinkdb.errors import ReqlAuthError, ReqlDriverError, ReqlRuntimeError

from scheduler.lib.resilient_scheduler import ResilientLoopMixin
from scheduler.lib.rethink_jobstore import ReconnectingRethinkDBJobStore

_SCHEDULER_PY = (
    Path(__file__).resolve().parents[1] / "src" / "scheduler" / "lib" / "scheduler.py"
)


class _Reply:
    """Answers every result shape the job store asks of a query."""

    def __contains__(self, item):
        return True

    def __iter__(self):
        return iter(())

    def __getitem__(self, key):
        return 1 if key in ("deleted", "replaced") else 0

    def keys(self):
        return ("replaced",)


class _FakeConn:
    """Minimal ``rethinkdb.net.Connection`` stand-in that can be killed."""

    def __init__(self):
        self.alive = True
        self.refuse_reconnect = False
        self.queries = 0
        self.reconnects = 0
        self.noreply_waits = []
        self.closes = 0

    def _start(self, term, **optargs):
        self.queries += 1
        if not self.alive:
            raise ReqlDriverError("Connection is closed.")
        return _Reply()

    def reconnect(self, noreply_wait=True, timeout=None):
        self.reconnects += 1
        self.noreply_waits.append(noreply_wait)
        if self.refuse_reconnect:
            raise ReqlDriverError("Could not connect to isard-db:28015.")
        self.alive = True

    def close(self, noreply_wait=True):
        self.closes += 1
        self.alive = False

    def is_open(self):
        return self.alive


@pytest.fixture
def store():
    conn = _FakeConn()
    store = ReconnectingRethinkDBJobStore(
        database="isard", table="scheduler_jobs", client=conn
    )
    store.start(None, "rethinkdb")
    yield store, conn
    store.shutdown()


def _now():
    return datetime.now(pytz.utc)


def test_get_due_jobs_recovers_after_the_connection_dies(store):
    """The wedge itself: a dead socket must not stop the due-jobs loop."""
    jobstore, conn = store
    assert jobstore.get_due_jobs(_now()) == []

    conn.alive = False
    assert jobstore.get_due_jobs(_now()) == []
    assert conn.reconnects == 1


def test_reconnect_never_waits_for_a_noreply_on_a_dead_socket(store):
    """``reconnect()`` defaults to noreply_wait=True, which raises before connecting."""
    jobstore, conn = store
    conn.alive = False
    jobstore.get_due_jobs(_now())
    assert conn.noreply_waits == [False]


@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda s: s.get_due_jobs(_now()), id="get_due_jobs"),
        pytest.param(lambda s: s.get_next_run_time(), id="get_next_run_time"),
        pytest.param(lambda s: s.get_all_jobs(), id="get_all_jobs"),
        pytest.param(lambda s: s.lookup_job("x"), id="lookup_job"),
        pytest.param(lambda s: s.remove_job("x"), id="remove_job"),
        pytest.param(lambda s: s.remove_all_jobs(), id="remove_all_jobs"),
    ],
)
def test_every_read_and_delete_method_recovers(store, call):
    """A store healing only get_due_jobs kills the greenlet on update_job."""
    jobstore, conn = store
    conn.alive = False
    call(jobstore)
    assert conn.reconnects == 1


def test_write_methods_recover(store):
    """add_job/update_job are the booking and desktop registration path."""
    jobstore, conn = store

    class _Job:
        id = "probe"
        next_run_time = _now()

        def __getstate__(self):
            return {"id": "probe"}

    conn.alive = False
    jobstore.add_job(_Job())
    assert conn.reconnects == 1

    conn.alive = False
    jobstore.update_job(_Job())
    assert conn.reconnects == 2


def test_bad_credentials_are_not_retried(store):
    """Reconnecting cannot fix an auth error, and retrying it would hammer the db."""
    jobstore, conn = store

    def _auth_error(term, **optargs):
        raise ReqlAuthError("Wrong password")

    conn._start = _auth_error
    with pytest.raises(ReqlAuthError):
        jobstore.get_due_jobs(_now())
    assert conn.reconnects == 0


def test_server_side_errors_are_left_to_apscheduler(store):
    """A missing table on a db that is still starting is not a dead connection."""
    jobstore, conn = store

    def _runtime_error(term, **optargs):
        raise ReqlRuntimeError("Table `isard.scheduler_jobs` does not exist.")

    conn._start = _runtime_error
    with pytest.raises(ReqlRuntimeError):
        jobstore.get_due_jobs(_now())
    assert conn.reconnects == 0


def test_a_refused_reconnect_backs_off_instead_of_retrying_every_tick(store):
    """While the db is down the 10 s tick must not pay a connect attempt each time."""
    jobstore, conn = store
    conn.alive = False
    conn.refuse_reconnect = True

    with pytest.raises(ReqlDriverError):
        jobstore.get_due_jobs(_now())
    assert conn.reconnects == 1

    with pytest.raises(ReqlDriverError):
        jobstore.get_due_jobs(_now())
    assert conn.reconnects == 1, "second attempt should have been gated by the backoff"


def test_recovery_after_a_refused_reconnect_resets_the_backoff(store):
    """A store that stayed backed off after recovery would heal slower each time."""
    jobstore, conn = store
    conn.alive = False
    conn.refuse_reconnect = True
    with pytest.raises(ReqlDriverError):
        jobstore.get_due_jobs(_now())

    jobstore._retry_not_before = 0.0
    conn.refuse_reconnect = False
    assert jobstore.get_due_jobs(_now()) == []
    assert jobstore._backoff_s == 1.0
    assert jobstore._retry_not_before == 0.0


def test_survives_repeated_flapping(store):
    """One recovery is luck; the db restarting five times is the real test."""
    jobstore, conn = store
    for expected in range(1, 6):
        conn.alive = False
        assert jobstore.get_due_jobs(_now()) == []
        assert conn.reconnects == expected


def test_disconnected_seconds_tracks_the_outage(store):
    """The healthcheck reads this, so it must be 0 while the store is healthy."""
    jobstore, conn = store
    assert jobstore.disconnected_seconds == 0.0

    conn.alive = False
    conn.refuse_reconnect = True
    with pytest.raises(ReqlDriverError):
        jobstore.get_due_jobs(_now())
    assert jobstore.disconnected_seconds > 0.0

    jobstore._retry_not_before = 0.0
    conn.refuse_reconnect = False
    jobstore.get_due_jobs(_now())
    assert jobstore.disconnected_seconds == 0.0


def test_shutdown_does_not_raise_on_an_already_dead_connection(store):
    """``RethinkDBJobStore.shutdown`` closes with a noreply wait, which raises."""
    jobstore, conn = store
    conn.alive = False
    jobstore.shutdown()
    assert jobstore.conn is None


def _init_body():
    tree = ast.parse(_SCHEDULER_PY.read_text())
    cls = next(
        n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Scheduler"
    )
    return tree, next(
        n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__init__"
    )


def test_production_builds_the_reconnecting_store():
    """Pin the wiring: the behaviour above is worthless if main uses the stock store."""
    _, init = _init_body()
    assigned = [
        node.value.func.id
        for node in ast.walk(init)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
    ]
    assert "ReconnectingRethinkDBJobStore" in assigned
    assert "RethinkDBJobStore" not in assigned


def test_the_job_store_is_registered_under_a_string_alias():
    """The store used to be passed as the ALIAS, so a second, bare store was built.

    That bare store is what every log line printed as ``connection=None``, and it
    is what ``print_jobs()`` crashes on.
    """
    tree, init = _init_body()
    calls = [
        node
        for node in ast.walk(init)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "add_jobstore"
    ]
    assert len(calls) == 1
    store_arg, alias_arg = calls[0].args
    assert isinstance(store_arg, ast.Attribute) and store_arg.attr == "rStore"
    assert isinstance(alias_arg, ast.Name) and alias_arg.id == "JOBSTORE_ALIAS"
    assert not calls[0].keywords

    jobstore_kwargs = [
        kw.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "jobstore"
    ]
    assert jobstore_kwargs, "the add_job call sites must still name a job store"
    for value in jobstore_kwargs:
        assert isinstance(value, ast.Name) and value.id == "JOBSTORE_ALIAS"


class _FakeLoop:
    """Stands in for APScheduler's ``_process_jobs``/``jobstore_retry_interval``."""

    jobstore_retry_interval = 10.0

    def __init__(self):
        self.raise_next = False
        self.wait_seconds = 60.0
        self.calls = 0

    def _process_jobs(self):
        self.calls += 1
        if self.raise_next:
            raise ReqlDriverError("Connection is closed.")
        return self.wait_seconds


class _GuardedLoop(ResilientLoopMixin, _FakeLoop):
    pass


def test_the_main_loop_survives_a_job_store_error_apscheduler_does_not_guard():
    """``update_job`` and ``get_next_run_time`` sit outside APScheduler's try.

    Measured on the pinned apscheduler: one exception from either ends the
    greenlet for good while ``state`` still reads STATE_RUNNING — no log line,
    no event. That is worse than the wedge, so the loop must never see it.
    """
    loop = _GuardedLoop()
    assert loop._process_jobs() == 60.0

    loop.raise_next = True
    assert loop._process_jobs() == loop.jobstore_retry_interval

    loop.raise_next = False
    assert loop._process_jobs() == 60.0
    assert loop.calls == 3


def test_a_stalled_loop_is_visible_but_an_idle_one_is_not():
    """The healthcheck reads this, so a scheduler idling until tomorrow stays green."""
    loop = _GuardedLoop()
    loop._process_jobs()
    assert loop.stalled_seconds == 0.0

    loop._next_tick_due = time.monotonic() - 300
    assert loop.stalled_seconds > 299

    loop.wait_seconds = None
    loop._process_jobs()
    assert loop.stalled_seconds == 0.0


def test_production_uses_the_guarded_scheduler():
    """Pin the wiring: a plain GeventScheduler puts the silent-death path back."""
    _, init = _init_body()
    built = [
        node.value.func.id
        for node in ast.walk(init)
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
    ]
    assert "ResilientGeventScheduler" in built
    assert "GeventScheduler" not in built


def test_the_production_path_builds_a_new_connection_and_closes_the_dead_one():
    """The shipped branch: build a fresh bounded connection, not reconnect() the dead one."""
    jobstore = ReconnectingRethinkDBJobStore(
        database="isard", table="scheduler_jobs", host="isard-db", port=28015
    )
    opened = []

    def _fake_connect(**kwargs):
        conn = _FakeConn()
        opened.append((conn, kwargs))
        return conn

    jobstore.r.connect = _fake_connect
    jobstore.start(None, "rethinkdb")
    assert len(opened) == 1

    first = opened[0][0]
    first.alive = False
    assert jobstore.get_due_jobs(_now()) == []

    assert (
        len(opened) == 2
    ), "the store must open a new connection, not reuse the dead one"
    assert first.closes == 1
    assert first.reconnects == 0
    assert opened[1][1]["timeout"] == 5.0
    assert jobstore.conn is opened[1][0]


def test_the_table_term_survives_a_reconnect(store):
    """A store that rebuilt the term against the wrong db would still pass everything else."""
    jobstore, conn = store
    table_before = jobstore.table
    conn.alive = False
    jobstore.get_due_jobs(_now())
    assert jobstore.table is table_before
