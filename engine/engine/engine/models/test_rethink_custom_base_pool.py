"""Pin the contract of engine's pool-backed ``RethinkCustomBase``.

Engine's :class:`RethinkCustomBase` used to be a descriptor that
handed every thread a dedicated, never-released connection. After
P2 item 9 it mirrors ``_common``'s pool-backed shape: each
``with cls._rdb_context():`` block acquires one connection from
engine's ``ThreadSafeConnectionPool`` for the block's duration and
releases it on exit. These tests pin that behaviour so a regression
to the legacy thread-local-descriptor pattern (which leaked sockets
on every long-quiet thread) would fail loudly.

The conftest under ``engine/engine/conftest.py`` stubs
``engine.services.db.db`` for the dispatch tests; here we explicitly
load the real ``rethink_custom_base.py`` via ``importlib`` and inject
a fake pool so we can exercise the full acquire/release path without
touching libvirt or a live rdb server.
"""

import importlib.util
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SRC_DIR = Path(__file__).resolve().parents[1]


class _FakePool:
    """Minimal stand-in for the fork's ``ThreadSafeConnectionPool``.

    Tracks acquire/release so tests can assert each context block
    paired with exactly one acquire and one release. Models the
    "distinct connection per concurrent thread" contract by issuing
    fresh ``MagicMock`` connections on every acquire that finds the
    idle pool empty.
    """

    def __init__(self, max_size: int = 50) -> None:
        self.max_size = max_size
        self._next_id = 0
        self._idle: list = []
        self._active: set = set()
        self._lock = threading.RLock()
        self.acquired: list = []
        self.acquire_timeouts: list = []
        self.released: list = []

    def acquire(self, timeout=None):
        # Pin that the new ``Context.__enter__`` always passes a
        # finite timeout — otherwise a saturated pool wedges the
        # caller instead of raising ``PoolExhaustedError``.
        self.acquire_timeouts.append(timeout)
        with self._lock:
            if self._idle:
                conn = self._idle.pop()
            else:
                if len(self._active) >= self.max_size:
                    raise RuntimeError(f"Pool exhausted (max_size={self.max_size})")
                conn = MagicMock(name=f"FakeConn-{self._next_id}")
                conn.id = self._next_id
                self._next_id += 1
            self._active.add(conn)
            self.acquired.append(conn)
            return conn

    def release(self, conn) -> None:
        with self._lock:
            if conn in self._active:
                self._active.remove(conn)
                self._idle.append(conn)
                self.released.append(conn)


def _load_rethink_custom_base(monkeypatch, fake_pool):
    """Stub heavy deps (``engine.services.db.db``, ``rethinkdb``) and
    load the real ``rethink_custom_base`` module via importlib so we
    can exercise the pool wiring with a deterministic fake pool."""
    # Stub engine.services.db.db so the module-level
    # ``from engine.services.db.db import connection_pool`` resolves
    # to our fake instead of opening a real socket.
    db_stub = MagicMock()
    db_stub.connection_pool = fake_pool
    monkeypatch.setitem(sys.modules, "engine.services.db", MagicMock())
    monkeypatch.setitem(sys.modules, "engine.services.db.db", db_stub)

    # ``isardvdi_common.connections.rethink_base`` does
    # ``from rethinkdb.errors import ReqlNonExistenceError`` at import
    # time. The ``rethinkdb`` top-level may already be stubbed by
    # the engine conftest as a bare ``MagicMock`` (no submodules),
    # which breaks ``rethinkdb.errors`` resolution. Inject a typed
    # stub so the import resolves to a real exception class — both
    # for the engine container's pytest run and host-side execution.
    import types as _types

    rethinkdb_real = _types.ModuleType("rethinkdb")
    rethinkdb_real.r = MagicMock(name="r")
    monkeypatch.setitem(sys.modules, "rethinkdb", rethinkdb_real)

    rethinkdb_errors = _types.ModuleType("rethinkdb.errors")

    class _ReqlNonExistenceError(Exception):
        pass

    rethinkdb_errors.ReqlNonExistenceError = _ReqlNonExistenceError
    monkeypatch.setitem(sys.modules, "rethinkdb.errors", rethinkdb_errors)

    # Drop any prior stub of engine.models.rethink_custom_base.
    sys.modules.pop("engine.models.rethink_custom_base", None)

    spec = importlib.util.spec_from_file_location(
        "engine.models.rethink_custom_base",
        str(_SRC_DIR / "models" / "rethink_custom_base.py"),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["engine.models.rethink_custom_base"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def fake_pool():
    return _FakePool(max_size=8)


@pytest.fixture
def rcb_module(monkeypatch, fake_pool):
    return _load_rethink_custom_base(monkeypatch, fake_pool)


def _concrete_subclass(rcb_module):
    """Concrete subclass of ``RethinkCustomBase`` that satisfies the
    abstract ``_rdb_table`` declared on :class:`RethinkBase`. Tests
    only need the pool-acquisition machinery, not Pydantic / id
    handling, so we don't subclass for inserts."""

    class _Doc(rcb_module.RethinkCustomBase):
        _rdb_table = "_test_doc"

    return _Doc


def test_context_enter_acquires_with_finite_timeout(rcb_module, fake_pool):
    """``Context.__enter__`` MUST pass a finite timeout to
    ``acquire``. Without one, a saturated pool wedges the worker
    indefinitely instead of raising ``PoolExhaustedError`` (the
    fork's ``ReqlDriverError`` subclass that engine's outer loops
    can catch and reconnect against)."""
    Doc = _concrete_subclass(rcb_module)

    with Doc._rdb_context():
        pass

    assert len(fake_pool.acquire_timeouts) == 1
    assert (
        fake_pool.acquire_timeouts[0] is not None and fake_pool.acquire_timeouts[0] > 0
    ), "acquire must pass a finite timeout, not None"


def test_context_block_releases_on_exit(rcb_module, fake_pool):
    """One acquire → one release per ``with`` block. Otherwise a
    pattern that opens many short blocks would leak slots and
    eventually saturate the pool."""
    Doc = _concrete_subclass(rcb_module)

    with Doc._rdb_context():
        pass

    assert len(fake_pool.acquired) == 1
    assert len(fake_pool.released) == 1
    assert fake_pool.acquired == fake_pool.released


def test_rdb_connection_reads_active_block_connection(rcb_module, fake_pool):
    """Inside a context block, ``cls._rdb_connection`` returns the
    pool-acquired connection. The class-level access path is what
    every ``_common`` ORM model uses — see the
    ``r.table(...).run(cls._rdb_connection)`` callsites."""
    Doc = _concrete_subclass(rcb_module)

    with Doc._rdb_context():
        conn = Doc._rdb_connection
        assert conn is fake_pool.acquired[-1]


def test_rdb_connection_is_none_outside_context(rcb_module, fake_pool):
    """Outside any active block AND with no test injection, the
    descriptor reads as None. This is a deliberate behaviour change
    from the legacy ``_ThreadLocalConnection`` which would always
    silently allocate — engine code that touches
    ``cls._rdb_connection`` outside a context block now visibly
    fails (``run(None)`` raises) instead of leaking a per-thread
    socket."""
    Doc = _concrete_subclass(rcb_module)

    # Sanity: nothing acquired yet.
    assert fake_pool.acquired == []
    assert Doc._rdb_connection is None


def test_nested_blocks_reuse_outermost_connection(rcb_module, fake_pool):
    """Nested ``with cls._rdb_context()`` calls in one thread MUST
    reuse the outermost block's connection and release only when
    the outermost block exits. Otherwise an ORM helper that opens
    its own block while called from another open block (a pattern
    used heavily in deployment / hypervisor models) would consume
    one slot per nesting level."""
    Doc = _concrete_subclass(rcb_module)

    with Doc._rdb_context():
        outer_conn = Doc._rdb_connection
        with Doc._rdb_context():
            inner_conn = Doc._rdb_connection
            assert inner_conn is outer_conn
        # Inner exit MUST NOT release — outer block still holds it.
        assert len(fake_pool.released) == 0
    # Outer exit releases.
    assert len(fake_pool.released) == 1
    assert fake_pool.released[0] is outer_conn


def test_concurrent_threads_get_distinct_connections(rcb_module, fake_pool):
    """The whole point of pooling: two threads holding open context
    blocks at the same time must each see their own connection.
    This is what would have caught the pre-pool bug where one
    thread's ``__exit__`` clobbered another thread's mid-flight
    connection."""
    Doc = _concrete_subclass(rcb_module)

    barrier = threading.Barrier(2)
    seen = []

    def _worker():
        with Doc._rdb_context():
            barrier.wait()  # both threads inside their block at once
            seen.append(Doc._rdb_connection)
            barrier.wait()

    with ThreadPoolExecutor(max_workers=2) as ex:
        f1 = ex.submit(_worker)
        f2 = ex.submit(_worker)
        f1.result(timeout=2)
        f2.result(timeout=2)

    assert len(seen) == 2
    assert seen[0] is not seen[1], "concurrent threads must hold distinct connections"


def test_setattr_injection_writes_per_thread_and_class_fallback(rcb_module, fake_pool):
    """Tests outside production code monkey-patch
    ``cls._rdb_connection`` to a mock. The setter MUST write the
    value into both the per-thread slot AND a process-wide class
    fallback so that ``asyncio.to_thread``-offloaded helpers (whose
    worker thread has an empty ``_thread_local``) still pick up
    the mock via the getter's fallback path."""
    Doc = _concrete_subclass(rcb_module)
    sentinel = MagicMock(name="injected-conn")

    # Inject from the main thread.
    Doc._rdb_connection = sentinel

    assert Doc._rdb_connection is sentinel
    # And a worker thread (with empty _thread_local) sees it via the
    # class-level fallback.
    seen = []

    def _worker():
        seen.append(Doc._rdb_connection)

    t = threading.Thread(target=_worker)
    t.start()
    t.join(timeout=1)

    assert seen == [sentinel]


def test_no_thread_local_connection_descriptor(rcb_module):
    """Pin that the legacy ``_ThreadLocalConnection`` class is gone.
    A regression that resurrects it would silently return to the
    "one socket per thread, never released" behaviour the migration
    eliminated."""
    assert not hasattr(rcb_module, "_ThreadLocalConnection"), (
        "_ThreadLocalConnection must not be re-introduced — the migration "
        "to a pool-backed Context is the whole point of P2 item 9."
    )
