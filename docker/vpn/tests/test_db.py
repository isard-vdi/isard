# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pin the contract of ``vpn.db.vpn_rethink_conn``.

The vpn service used to rely on ``r.connect(...).repl()`` setting a
process-global default connection — every ``r.table(...).run()`` call
reached for that thread-local. The new helper replaces that pattern
with a per-call ``with vpn_rethink_conn() as conn:`` acquired from
``isardvdi_common``'s ``ThreadSafeConnectionPool``.

These tests pin:

1. The helper acquires from the shared pool on entry.
2. The helper releases back to the pool on exit (also on exception).
3. Concurrent threads each get a distinct connection — pinning the
   guarantee the legacy ``.repl()`` pattern violated.
4. Re-entrancy: a nested ``with vpn_rethink_conn():`` reuses the
   outermost block's connection (matches ``_common.Context``'s
   semantics).
"""
from __future__ import annotations

import importlib.util
import sys
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent / "src"


def _load_real_db():
    """Load ``docker/vpn/src/db.py`` directly, bypassing the conftest
    stub that masks it for the other tests in this directory.

    The conftest's session-level stub of ``sys.modules['db']`` would
    otherwise intercept ``import db`` — we explicitly want the real
    module so we can verify it routes to ``_common``'s pool.
    """
    sys.modules.pop("db", None)
    spec = importlib.util.spec_from_file_location("db", str(SRC_DIR / "db.py"))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["db"] = module
    spec.loader.exec_module(module)
    return module


class _FakePool:
    """Minimal ``ThreadSafeConnectionPool`` stand-in mirroring the
    one used by the webapp/scheduler tests."""

    def __init__(self):
        self.acquired = []
        self.released = []
        self._lock = threading.RLock()
        self._next = 0

    def acquire(self, timeout=None):
        with self._lock:
            conn = MagicMock(name=f"FakeConn-{self._next}")
            conn.is_open = lambda _conn=conn: not getattr(_conn, "_closed", False)
            self._next += 1
            self.acquired.append(conn)
            return conn

    def release(self, conn):
        with self._lock:
            self.released.append(conn)


@pytest.fixture
def fake_pool():
    """Mount a fake pool on ``_common``'s shared module so the helper
    routes through it instead of opening a real socket."""
    from isardvdi_common.connections import rethink_shared_connection as mod

    pool = _FakePool()
    mod._set_pool_for_tests(pool)
    if hasattr(mod._thread_local, "conn"):
        del mod._thread_local.conn
    if hasattr(mod._thread_local, "depth"):
        del mod._thread_local.depth
    yield pool
    mod._set_pool_for_tests(None)
    if hasattr(mod._thread_local, "conn"):
        del mod._thread_local.conn
    if hasattr(mod._thread_local, "depth"):
        del mod._thread_local.depth


@pytest.fixture
def db_module():
    """Real ``db`` module under test."""
    return _load_real_db()


def test_acquires_and_releases_one_connection(db_module, fake_pool):
    """Single ``with`` block must acquire exactly one connection on
    entry and release it on exit."""
    with db_module.vpn_rethink_conn() as conn:
        assert conn is fake_pool.acquired[0]
        assert len(fake_pool.released) == 0

    assert len(fake_pool.released) == 1
    assert fake_pool.released[0] is fake_pool.acquired[0]


def test_release_runs_when_block_raises(db_module, fake_pool):
    """A pool slot leaked on every error would deplete the pool over
    time — the ``finally`` semantics of the ``with`` statement must
    release the connection even when the block body raises."""

    class _Boom(RuntimeError):
        pass

    with pytest.raises(_Boom):
        with db_module.vpn_rethink_conn():
            raise _Boom("simulated query failure")

    assert len(fake_pool.acquired) == 1
    assert len(fake_pool.released) == 1


def test_concurrent_threads_each_get_own_connection(db_module, fake_pool):
    """Two threads in their own ``with`` blocks must each acquire a
    distinct connection. The legacy ``.repl()`` pattern was unsafe
    here precisely because it set a process-global default."""
    barrier = threading.Barrier(2)
    seen = {}
    errors = []

    def worker(name):
        try:
            with db_module.vpn_rethink_conn() as conn:
                barrier.wait()
                seen[name] = conn
        except Exception as exc:
            errors.append(exc)

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert errors == []
    assert seen["a"] is not seen["b"]


def test_reentrancy_reuses_outer_connection(db_module, fake_pool):
    """A nested ``with vpn_rethink_conn():`` inside another must
    reuse the outer connection — pool acquire only on the outer
    enter, release only on the outer exit. Pinning this catches
    accidental regressions to the ``Context.__enter__`` depth-counter."""
    with db_module.vpn_rethink_conn() as outer:
        assert len(fake_pool.acquired) == 1
        with db_module.vpn_rethink_conn() as inner:
            # Same connection — re-entrancy reuses outer slot.
            assert inner is outer
            assert (
                len(fake_pool.acquired) == 1
            ), "nested with must NOT acquire a second connection"
        assert (
            len(fake_pool.released) == 0
        ), "inner with-exit must NOT release while outer is still open"

    assert len(fake_pool.released) == 1
