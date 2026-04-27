# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for the pool-backed RethinkSharedConnection shim.

These tests don't talk to RethinkDB. They mount a fake
``ThreadSafeConnectionPool`` over the module's pool slot via
``_set_pool_for_tests`` and assert the shim's behaviour:

* ``with cls._rdb_context()`` acquires from the pool on entry and
  releases on exit;
* concurrent threads each see their own connection during their
  context block;
* nested contexts within one thread reuse the outermost connection
  and only release once;
* ``cls._rdb_connection`` reads as ``None`` outside any context;
* :class:`RethinkCustomBase` (the diamond inheritance) instantiates
  cleanly — the abstract ``_rdb_connection`` declared by
  :class:`RethinkBase` is satisfied by the concrete property on
  :class:`RethinkSharedConnection`.

These contract pins are what would have caught the legacy bug where
two concurrent callers clobbered each other's ``_rdb_connection``
assignment.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import List
from unittest.mock import MagicMock

import pytest

# --------------------------------------------------------------------
# Fake pool — minimal subset of ThreadSafeConnectionPool's contract
# the shim depends on. Tracks acquire/release order so tests can
# assert the right number of distinct connections were handed out.
# --------------------------------------------------------------------


class _FakePool:
    def __init__(self, max_size: int = 10) -> None:
        self.max_size = max_size
        self._next_id = 0
        self._idle: list = []
        self._active: set = set()
        self._lock = threading.RLock()
        self.acquired: List = []
        self.released: List = []
        self.closed = False

    def acquire(self, timeout=None):
        with self._lock:
            if self._idle:
                conn = self._idle.pop()
            else:
                if len(self._active) >= self.max_size:
                    raise RuntimeError(f"Pool exhausted (max_size={self.max_size})")
                conn = MagicMock(name=f"FakeConn-{self._next_id}")
                conn.id = self._next_id
                conn.is_open = lambda _conn=conn: not getattr(_conn, "_closed", False)
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

    def close(self) -> None:
        with self._lock:
            self.closed = True
            self._idle.clear()
            self._active.clear()


@pytest.fixture
def fake_pool():
    """Inject a fresh fake pool for each test and tear it down."""
    from isardvdi_common.connections import rethink_shared_connection as mod

    pool = _FakePool()
    mod._set_pool_for_tests(pool)
    # Also make sure no thread-local state leaks across tests.
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


# --------------------------------------------------------------------
# Tests
# --------------------------------------------------------------------


def test_context_acquires_on_enter_and_releases_on_exit(fake_pool):
    from isardvdi_common.connections.rethink_shared_connection import (
        RethinkSharedConnection,
    )

    assert RethinkSharedConnection._rdb_connection is None
    with RethinkSharedConnection._rdb_context():
        conn = RethinkSharedConnection._rdb_connection
        assert conn is not None
        assert conn in fake_pool.acquired
        assert conn not in fake_pool.released
    assert RethinkSharedConnection._rdb_connection is None
    assert fake_pool.released[-1] is conn


def test_nested_context_reuses_outer_connection(fake_pool):
    """Re-entrancy: nested ``with`` blocks within the same thread
    must share one connection. Otherwise legacy code that calls
    helpers from inside its own ``with cls._rdb_context()`` block
    would deadlock or exhaust the pool."""
    from isardvdi_common.connections.rethink_shared_connection import (
        RethinkSharedConnection,
    )

    with RethinkSharedConnection._rdb_context():
        outer = RethinkSharedConnection._rdb_connection
        with RethinkSharedConnection._rdb_context():
            inner = RethinkSharedConnection._rdb_connection
            assert inner is outer
        # Inner exit must NOT release; outer block still holds the conn.
        assert outer not in fake_pool.released
    assert outer in fake_pool.released


def test_concurrent_threads_get_distinct_connections(fake_pool):
    """The legacy bug: two threads sharing one ``_rdb_connection``
    class attribute would clobber each other and the first to exit
    would close the connection the other was still using mid-query.
    Each thread must now see its own pool-acquired connection."""
    from isardvdi_common.connections.rethink_shared_connection import (
        RethinkSharedConnection,
    )

    seen_per_thread = {}
    barrier = threading.Barrier(5)

    def worker(idx):
        barrier.wait()  # all five threads enter the context simultaneously
        with RethinkSharedConnection._rdb_context():
            # Mid-block, hold the conn briefly so concurrency is visible.
            seen_per_thread[idx] = RethinkSharedConnection._rdb_connection
            time.sleep(0.05)
            return RethinkSharedConnection._rdb_connection

    with ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(worker, range(5)))

    assert len(set(id(c) for c in results)) == 5, (
        "expected five distinct connections, got " f"{[c.id for c in results]}"
    )
    # All five connections should have been acquired AND released.
    assert len(fake_pool.acquired) == 5
    assert len(fake_pool.released) == 5


def test_connection_is_none_outside_any_context(fake_pool):
    from isardvdi_common.connections.rethink_shared_connection import (
        RethinkSharedConnection,
    )

    assert RethinkSharedConnection._rdb_connection is None


def test_context_releases_even_if_block_raises(fake_pool):
    """Connection leak guard: an exception inside the block must
    still release the connection so the pool doesn't drain over time."""
    from isardvdi_common.connections.rethink_shared_connection import (
        RethinkSharedConnection,
    )

    class _Boom(Exception):
        pass

    with pytest.raises(_Boom):
        with RethinkSharedConnection._rdb_context():
            conn = RethinkSharedConnection._rdb_connection
            raise _Boom()
    assert conn in fake_pool.released
    assert RethinkSharedConnection._rdb_connection is None


def test_rethink_custom_base_satisfies_abstract_rdb_connection(fake_pool):
    """``RethinkBase`` declares ``_rdb_connection`` as a
    ``@property @abstractmethod``. Instantiating
    :class:`RethinkCustomBase` (which combines
    :class:`RethinkSharedConnection` and :class:`RethinkBase`) must
    succeed — i.e. the abstract requirement is satisfied by the
    concrete property on :class:`RethinkSharedConnection` that
    routes to the pool-acquired connection."""
    from isardvdi_common.connections.rethink_custom_base import RethinkCustomBase

    # We don't actually need to *instantiate* ``RethinkCustomBase``
    # itself — its constructor expects an existing document — but we
    # can probe the abstractness of the class. A class that has
    # un-implemented abstract methods would fail
    # ``__abstractmethods__``-emptiness here.
    assert "_rdb_connection" not in RethinkCustomBase.__abstractmethods__


def test_pool_close_swallows_secondary_errors_during_atexit(fake_pool):
    """``_rethink_disconnect`` is doubly-decorated (``@classmethod`` over
    the ``atexit_register`` classmethod subclass) so the registered
    callable runs at process exit. Direct callable lookup goes through
    the descriptor chain awkwardly; bypass via ``__func__`` to exercise
    the swallow-secondary-errors contract that the atexit dispatcher
    relies on (atexit must not be interrupted by raise from one hook)."""
    from isardvdi_common.connections import rethink_shared_connection as mod

    fake_pool.close = MagicMock(side_effect=RuntimeError("simulated"))
    # Pull the unwrapped function out of the descriptor chain.
    inner = mod.RethinkSharedConnection.__dict__["_rethink_disconnect"]
    # Walk through ``classmethod`` -> ``atexit_register`` -> raw function.
    while hasattr(inner, "__func__"):
        inner = inner.__func__
    # Should NOT propagate — atexit must not be interrupted.
    inner(mod.RethinkSharedConnection)
