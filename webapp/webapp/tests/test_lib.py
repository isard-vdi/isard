#
#   Copyright © 2026 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

import threading
from unittest.mock import MagicMock

import pytest
from flask import Flask, g

from webapp.lib.flask_rethink import RDB
from webapp.lib.load_config import load_config, loadConfig

# ──────────────────────────────────────────────────────────────────────
# load_config — env-var driven Flask config loader
# ──────────────────────────────────────────────────────────────────────


def test_load_config_returns_log_level_from_env(monkeypatch):
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    assert load_config() == {"LOG_LEVEL": "DEBUG"}


def test_load_config_defaults_log_level_to_info(monkeypatch):
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    assert load_config() == {"LOG_LEVEL": "INFO"}


def test_loadconfig_init_app_sets_required_keys(monkeypatch):
    monkeypatch.setenv("HOSTNAME", "test-host")
    monkeypatch.setenv("LOG_LEVEL", "DEBUG")
    fresh = Flask(__name__)
    cfg = loadConfig()

    assert cfg.init_app(fresh) is True
    assert fresh.config["HOSTNAME"] == "test-host"
    assert fresh.config["SESSION_COOKIE_NAME"] == "isard-admin"
    assert fresh.config["LOG_LEVEL"] == "DEBUG"
    assert fresh.config["url"] == "http://www.isardvdi.com:5050"
    assert fresh.debug is True


def test_loadconfig_init_app_defaults_log_level_to_info(monkeypatch):
    monkeypatch.setenv("HOSTNAME", "test-host")
    monkeypatch.delenv("LOG_LEVEL", raising=False)
    fresh = Flask(__name__)

    loadConfig().init_app(fresh)

    assert fresh.config["LOG_LEVEL"] == "INFO"
    assert fresh.debug is False


def test_loadconfig_init_app_calls_exit_when_hostname_missing(monkeypatch):
    monkeypatch.delenv("HOSTNAME", raising=False)
    fresh = Flask(__name__)

    # The except block calls exit() which raises SystemExit.
    with pytest.raises(SystemExit):
        loadConfig().init_app(fresh)


# ──────────────────────────────────────────────────────────────────────
# RDB — Flask extension wrapper for the rethinkdb shared pool
#
# The extension delegates connection acquisition to
# ``isardvdi_common.connections.rethink_shared_connection``'s
# ``ThreadSafeConnectionPool``. The tests inject a fake pool through
# ``_set_pool_for_tests`` (the module-private test seam) so no real
# rdb sockets open and we can assert acquire/release symmetry.
# ──────────────────────────────────────────────────────────────────────


class _FakePool:
    """Minimal ``ThreadSafeConnectionPool`` stand-in.

    Hands out a fresh ``MagicMock`` on each acquire, tracks acquires
    + releases for assertion, and refuses to reuse a connection until
    it's released.
    """

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
    fresh.config.update(
        RETHINKDB_HOST="db",
        RETHINKDB_PORT=28015,
        RETHINKDB_DB="isard",
    )

    rdb = RDB(fresh)

    assert rdb.app is fresh
    assert fresh.teardown_appcontext_funcs, "teardown handler must be registered"


def test_rdb_init_without_app_skips_init():
    """RDB() with no app must not register teardown — used in
    lazy-init code paths that wire the extension after Flask config."""
    rdb = RDB()
    assert rdb.app is None
    assert rdb.db is None


def test_rdb_conn_acquires_from_pool_and_caches_per_request(fake_pool):
    """First ``db.conn`` access in a request enters the pool's
    Context (acquiring one connection). Subsequent accesses in the
    same request return the cached connection — only one pool
    acquire per request."""
    fresh = Flask(__name__)
    fresh.config.update(RETHINKDB_DB="isard")
    rdb = RDB(fresh)

    with fresh.app_context():
        c1 = rdb.conn
        c2 = rdb.conn

    assert c1 is c2, "second access must return the cached connection"
    assert (
        len(fake_pool.acquired) == 1
    ), "exactly one acquire per request — extra acquires defeat the pool"


def test_rdb_teardown_releases_pool_connection(fake_pool):
    """When the Flask app-context exits, the per-request connection
    must be released back to the pool — a leak here would deplete
    the pool over time."""
    fresh = Flask(__name__)
    fresh.config.update(RETHINKDB_DB="isard")
    rdb = RDB(fresh)

    with fresh.app_context():
        _ = rdb.conn
        # Inside the context, acquire is recorded but release is not.
        assert len(fake_pool.acquired) == 1
        assert len(fake_pool.released) == 0

    # After context exit, release runs.
    assert len(fake_pool.released) == 1
    assert (
        fake_pool.released[0] is fake_pool.acquired[0]
    ), "release must return the same connection that was acquired"


def test_rdb_teardown_noop_without_connection(fake_pool):
    """If the request never calls ``db.conn``, no pool slot was
    acquired and the teardown must run without raising and without
    spurious releases."""
    fresh = Flask(__name__)
    fresh.config.update(RETHINKDB_DB="isard")
    RDB(fresh)

    with fresh.app_context():
        pass  # no db.conn use

    assert fake_pool.acquired == []
    assert fake_pool.released == []


def test_rdb_db_kwarg_matching_default_works(fake_pool):
    """Passing the same db as the Flask config is a no-op — kept
    for source compatibility with old call sites."""
    fresh = Flask(__name__)
    fresh.config.update(RETHINKDB_DB="isard")
    rdb = RDB(fresh, db="isard")

    with fresh.app_context():
        c = rdb.conn

    assert c is fake_pool.acquired[0]


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


def test_rdb_concurrent_requests_each_get_their_own_connection(fake_pool):
    """Two concurrent requests must each acquire a distinct
    connection — the pool is per-thread underneath, and Flask
    handles requests on separate threads. A regression here would
    bring back the pre-pool clobbering bug.
    """
    fresh = Flask(__name__)
    fresh.config.update(RETHINKDB_DB="isard")
    rdb = RDB(fresh)

    barrier = threading.Barrier(2)
    seen = {}
    errors = []

    def worker(name):
        try:
            with fresh.app_context():
                # All threads enter the conn property together so the
                # pool issues two distinct acquires concurrently.
                barrier.wait()
                seen[name] = rdb.conn
        except Exception as exc:  # surface any error in the test
            errors.append(exc)

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert errors == []
    assert len(seen) == 2
    assert seen["a"] is not seen["b"], "concurrent requests must not share a connection"
