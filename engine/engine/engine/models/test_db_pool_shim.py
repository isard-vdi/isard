"""Pin the contract of the engine's pool-backed legacy shim.

``engine/services/db/db.py`` exposes two legacy functions every pre-pool
callsite uses:

- ``new_rethink_connection()`` used to do ``r.connect(...)`` (fresh socket)
- ``close_rethink_connection(r_conn)`` used to do ``r_conn.close()``
  (terminates the socket)

The current shim routes both through the fork's
``ThreadSafeConnectionPool`` so all 90+ legacy callsites get pooled
connections without any callsite changes. These tests pin that contract
so a future refactor doesn't accidentally regress to ``r.connect(...)``-
per-call. The pool exposes ``acquire(timeout=...)`` / ``release(...)``;
pre-Phase-2 the engine had its own pool with ``get_connection()`` /
``release_connection()`` semantics — these tests now assert the new
fork-pool surface so a regression that resurrects the hand-rolled
queue-backed pool would fail loudly.

The conftest under ``engine/engine/conftest.py`` stubs
``engine.services.db.db`` for the dispatch tests; here we explicitly
load the *real* module via ``importlib`` so we can exercise it.
"""

import importlib.util
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

_SRC_DIR = Path(__file__).resolve().parents[1]


def _load_real_db_module(monkeypatch):
    """Drop the conftest stub and load the real ``engine.services.db.db``
    via importlib. Stubs the heavy imports the real module pulls in so
    we don't need libvirt / paramiko / a live rethinkdb."""
    # Stub engine.config + log so the real db.py imports cleanly.
    cfg = MagicMock()
    cfg.RETHINK_DB = "isard"
    cfg.RETHINK_HOST = "isard-db"
    cfg.RETHINK_PORT = 28015
    cfg.MAX_QUEUE_DOMAINS_STATUS = 16
    monkeypatch.setitem(sys.modules, "engine.config", cfg)

    log_mod = MagicMock()
    monkeypatch.setitem(sys.modules, "engine.services.log", log_mod)

    # Stub the rethinkdb top-level module — the shim only calls
    # ``connection_pool.acquire()`` / ``release()``; we replace
    # ``connection_pool`` with a fake before reading the shim, so
    # ``r.connect(...)`` etc. is never reached at runtime. The fork's
    # ``ThreadSafeConnectionPool`` lives under ``rethinkdb.connection_pool``;
    # stub that submodule too so the import at module load doesn't blow up.
    rethinkdb_mod = MagicMock()
    monkeypatch.setitem(sys.modules, "rethinkdb", rethinkdb_mod)

    pool_mod = MagicMock()

    class _StubThreadSafeConnectionPool:
        """Captures the construction args so we can pin them, but
        never actually opens a socket — production code will replace
        this instance with ``fake_pool`` before the first acquire."""

        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

        def acquire(self, timeout=None):  # pragma: no cover - replaced
            raise RuntimeError("fake_pool fixture must replace this")

        def release(self, conn):  # pragma: no cover - replaced
            raise RuntimeError("fake_pool fixture must replace this")

    pool_mod.ThreadSafeConnectionPool = _StubThreadSafeConnectionPool
    monkeypatch.setitem(sys.modules, "rethinkdb.connection_pool", pool_mod)

    # ``engine.services.db.db`` imports the slow-/failed-query observer
    # from ``isardvdi_common.connections.rethink_shared_connection``.
    # That module pulls in the whole shared-pool + atexit machinery —
    # which is irrelevant to the shim contract. Stub the import target
    # to a bare module exporting just the symbol we need.
    shared_stub = MagicMock()
    shared_stub._query_observer_on_end = lambda *a, **kw: None
    monkeypatch.setitem(
        sys.modules,
        "isardvdi_common.connections.rethink_shared_connection",
        shared_stub,
    )

    # Drop any prior conftest stub of engine.services.db.db.
    sys.modules.pop("engine.services.db.db", None)

    spec = importlib.util.spec_from_file_location(
        "engine.services.db.db",
        str(_SRC_DIR / "services" / "db" / "db.py"),
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["engine.services.db.db"] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def db_module(monkeypatch):
    return _load_real_db_module(monkeypatch)


@pytest.fixture
def fake_pool(db_module):
    """Replace the module's ``connection_pool`` with a stand-in that
    records every acquire/release the shim makes."""
    pool = MagicMock()
    sentinel_conn = MagicMock(name="pool-conn")
    pool.acquire.return_value = sentinel_conn
    db_module.connection_pool = pool
    return pool


def test_new_rethink_connection_acquires_from_pool(db_module, fake_pool):
    """``new_rethink_connection()`` must reach into the pool, not
    open a fresh socket. Pinning this catches a regression to the
    legacy ``r.connect(RETHINK_HOST, RETHINK_PORT, db=...)`` body.
    The acquire MUST pass a finite timeout so pool exhaustion fails
    fast as ``PoolExhaustedError`` instead of wedging."""
    conn = db_module.new_rethink_connection()

    fake_pool.acquire.assert_called_once()
    # The shim passes the env-tunable timeout positionally OR by
    # keyword — accept either, but require some non-None timeout.
    call = fake_pool.acquire.call_args
    timeout = (
        call.kwargs.get("timeout")
        if call.kwargs
        else (call.args[0] if call.args else None)
    )
    assert timeout is not None and timeout > 0, "acquire must pass a finite timeout"
    assert conn is fake_pool.acquire.return_value


def test_close_rethink_connection_releases_to_pool(db_module, fake_pool):
    """``close_rethink_connection(r_conn)`` must release the slot
    back to the pool. The legacy code did ``r_conn.close()``, which
    terminated the socket — that's what we explicitly DON'T want
    anymore."""
    conn = MagicMock(name="held-conn")

    result = db_module.close_rethink_connection(conn)

    fake_pool.release.assert_called_once_with(conn)
    # Legacy callers propagated the True return; preserve that contract.
    assert result is True
    # And the shim must NOT call .close() on the connection — that
    # would be a regression that drops the socket the pool is
    # actively recycling.
    conn.close.assert_not_called()


def test_close_rethink_connection_tolerates_none(db_module, fake_pool):
    """A handful of legacy callsites set ``r_conn = None`` on an
    error path then call ``close_rethink_connection(r_conn)``; the
    shim must not raise."""
    result = db_module.close_rethink_connection(None)

    fake_pool.release.assert_not_called()
    assert result is True


def test_rethink_decorator_uses_pool_via_shim(db_module, fake_pool):
    """The ``@rethink`` decorator wraps a function with acquire +
    release-via-finally. After the shim, both go through the pool —
    pinning that the decorator's internals haven't drifted away."""
    seen_conn = []

    @db_module.rethink
    def inner(conn, x):
        seen_conn.append(conn)
        return x * 2

    out = inner(7)

    assert out == 14
    assert seen_conn == [fake_pool.acquire.return_value]
    fake_pool.acquire.assert_called_once()
    fake_pool.release.assert_called_once_with(fake_pool.acquire.return_value)


def test_rethink_decorator_releases_on_exception(db_module, fake_pool):
    """The ``finally`` clause in the decorator must run even when
    the wrapped function raises. Otherwise an in-flight error would
    leak a pool slot per failure."""

    @db_module.rethink
    def boom(conn):
        raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        boom()

    fake_pool.release.assert_called_once_with(fake_pool.acquire.return_value)


def test_rethink_conn_context_manager_uses_pool(db_module, fake_pool):
    """``with rethink_conn() as conn:`` must acquire from the pool
    on entry and release on exit, including when the body raises.
    Pinning this catches a regression that drops the ``finally`` and
    leaks a slot per failure inside the ``with`` block."""
    seen = []

    with db_module.rethink_conn() as conn:
        seen.append(conn)

    assert seen == [fake_pool.acquire.return_value]
    fake_pool.acquire.assert_called_once()
    fake_pool.release.assert_called_once_with(fake_pool.acquire.return_value)


def test_rethink_conn_releases_on_body_exception(db_module, fake_pool):
    """The context manager's release path must run even when the body
    raises — otherwise a single mid-block failure permanently leaks
    a pool slot. Mirrors the ``@rethink`` decorator's invariant."""
    with pytest.raises(RuntimeError, match="body boom"):
        with db_module.rethink_conn():
            raise RuntimeError("body boom")

    fake_pool.release.assert_called_once_with(fake_pool.acquire.return_value)
