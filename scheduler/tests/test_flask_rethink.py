# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin the scheduler's ``RDB`` Flask extension's pool-backed contract.

Mirrors the webapp's ``flask_rethink`` test surface — both modules
implement the same protocol against the shared
``ThreadSafeConnectionPool`` from ``isardvdi_common``. Cross-service
divergence here would let a connection leak in scheduler hide
behind webapp tests passing.

The fake pool is mounted via ``_set_pool_for_tests`` (the module's
documented test seam) so no real rdb sockets open.
"""

import threading
from unittest.mock import MagicMock

import pytest
from flask import Flask

from scheduler.lib.flask_rethink import RDB


class _FakePool:
    """Minimal ``ThreadSafeConnectionPool`` stand-in. Hands out a
    fresh ``MagicMock`` per acquire and tracks acquire/release order
    so the tests can assert symmetry."""

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
    """Mount a fresh fake pool for each test and clean up after."""
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


def test_rdb_init_with_app_registers_teardown():
    fresh = Flask(__name__)
    fresh.config.update(RETHINKDB_DB="isard")
    rdb = RDB(fresh)

    assert rdb.app is fresh
    assert fresh.teardown_appcontext_funcs, "teardown handler must be registered"


def test_rdb_init_without_app_skips_init():
    """``RDB()`` with no app must not register teardown — used in the
    ``RDB(app)`` then ``db.init_app(app)`` lazy-init pattern in
    ``scheduler/lib/scheduler.py``."""
    rdb = RDB()
    assert rdb.app is None
    assert rdb.db is None


def test_rdb_conn_acquires_from_pool_and_caches_per_context(fake_pool):
    """First access acquires; subsequent accesses in the same
    Flask app context return the cached connection. Critical for
    scheduler: ``Scheduler.__init__`` makes 8+ ``db.conn`` reads
    inside one ``with app.app_context()`` block per default-job."""
    fresh = Flask(__name__)
    fresh.config.update(RETHINKDB_DB="isard")
    rdb = RDB(fresh)

    with fresh.app_context():
        c1 = rdb.conn
        c2 = rdb.conn

    assert c1 is c2
    assert (
        len(fake_pool.acquired) == 1
    ), "exactly one acquire per context — extra acquires defeat the pool"


def test_rdb_teardown_releases_pool_connection(fake_pool):
    """When ``with app.app_context()`` exits, the connection must be
    released. A leak here would deplete the pool over scheduler
    uptime (jobs run for the lifetime of the process)."""
    fresh = Flask(__name__)
    fresh.config.update(RETHINKDB_DB="isard")
    rdb = RDB(fresh)

    with fresh.app_context():
        _ = rdb.conn
        assert len(fake_pool.acquired) == 1
        assert len(fake_pool.released) == 0

    assert len(fake_pool.released) == 1
    assert fake_pool.released[0] is fake_pool.acquired[0]


def test_rdb_teardown_noop_without_connection(fake_pool):
    """A context that never touches ``db.conn`` must not acquire."""
    fresh = Flask(__name__)
    fresh.config.update(RETHINKDB_DB="isard")
    RDB(fresh)

    with fresh.app_context():
        pass

    assert fake_pool.acquired == []
    assert fake_pool.released == []


def test_rdb_db_kwarg_mismatch_raises(fake_pool):
    """Passing a different db than RETHINKDB_DB must raise — the
    pool is process-global to one DB and silent fallback would
    confuse callers."""
    fresh = Flask(__name__)
    fresh.config.update(RETHINKDB_DB="isard")
    rdb = RDB(fresh, db="other-db")

    with fresh.app_context():
        with pytest.raises(RuntimeError, match="does not match the pool"):
            _ = rdb.conn

    assert fake_pool.acquired == []


def test_rdb_consecutive_app_contexts_acquire_separately(fake_pool):
    """Two sequential ``with app.app_context()`` blocks each acquire
    + release independently — pinning that the cache is per-context,
    not per-instance. ``Scheduler`` startup uses this pattern for
    each default-job seed; an instance-level cache would leak the
    first request's connection."""
    fresh = Flask(__name__)
    fresh.config.update(RETHINKDB_DB="isard")
    rdb = RDB(fresh)

    with fresh.app_context():
        _ = rdb.conn

    with fresh.app_context():
        _ = rdb.conn

    assert (
        len(fake_pool.acquired) == 2
    ), "each ``with app.app_context()`` block must acquire its own connection"
    assert len(fake_pool.released) == 2
