# Copyright 2017 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
#      Alberto Larraz Dalmases
# License: AGPLv3

#!/usr/bin/env python
# coding=utf-8

import logging as log
import time

import gevent
from flask import _app_ctx_stack as stack
from flask import current_app
from gevent.lock import BoundedSemaphore
from gevent.queue import Empty, Queue
from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

r = RethinkDB()

# Global pool instance
_pool = None


class PooledConnection:
    """Wrapper for a RethinkDB connection with creation timestamp."""

    __slots__ = ("conn", "created_at")

    def __init__(self, conn):
        self.conn = conn
        self.created_at = time.time()

    def __getattr__(self, name):
        return getattr(self.conn, name)


class ConnectionPool:
    """RethinkDB connection pool using gevent primitives."""

    def __init__(
        self,
        host,
        port,
        db,
        auth_key="",
        pool_size=32,
        conn_ttl=3600,
        cleanup_interval=60,
    ):
        self._host = host
        self._port = int(port)
        self._db = db
        self._auth_key = auth_key
        self._pool_size = pool_size
        self._conn_ttl = conn_ttl
        self._cleanup_interval = cleanup_interval

        self._queue = Queue()
        self._semaphore = BoundedSemaphore(pool_size)
        self._total_created = 0
        self._shutdown = False
        self._cleanup_greenlet = gevent.spawn(self._cleanup_loop)

    def _create_connection(self):
        """Create a new RethinkDB connection."""
        conn = r.connect(
            host=self._host,
            port=self._port,
            db=self._db,
            auth_key=self._auth_key,
        )
        self._total_created += 1
        log.debug(f"Created new RethinkDB connection (total: {self._total_created})")
        return PooledConnection(conn)

    def _is_valid(self, pooled_conn):
        """Check if a connection is still valid (not expired, not closed)."""
        if pooled_conn is None:
            return False
        age = time.time() - pooled_conn.created_at
        if age > self._conn_ttl:
            return False
        try:
            return pooled_conn.conn.is_open()
        except Exception:
            return False

    def _close_connection(self, pooled_conn):
        """Safely close a connection."""
        try:
            if pooled_conn and pooled_conn.conn:
                pooled_conn.conn.close()
        except Exception as e:
            log.debug(f"Error closing connection: {e}")

    def acquire(self, timeout=30):
        """
        Acquire a connection from the pool.

        If no connection is available and pool is not at capacity, creates a new one.
        Raises Empty if timeout expires before a connection is available.
        """
        deadline = time.time() + timeout if timeout else None

        while True:
            # Try to get an existing connection from queue
            try:
                pooled_conn = self._queue.get_nowait()
                if self._is_valid(pooled_conn):
                    return pooled_conn.conn
                else:
                    self._close_connection(pooled_conn)
                    self._semaphore.release()
            except Empty:
                pass

            # Try to create a new connection if under limit
            if self._semaphore.acquire(blocking=False):
                try:
                    pooled_conn = self._create_connection()
                    return pooled_conn.conn
                except Exception as e:
                    self._semaphore.release()
                    log.error(f"Failed to create RethinkDB connection: {e}")
                    raise

            # Wait for a connection to become available
            remaining = deadline - time.time() if deadline else None
            if remaining is not None and remaining <= 0:
                raise Empty("Connection pool timeout")

            try:
                wait_time = min(remaining, 1.0) if remaining else 1.0
                pooled_conn = self._queue.get(timeout=wait_time)
                if self._is_valid(pooled_conn):
                    return pooled_conn.conn
                else:
                    self._close_connection(pooled_conn)
                    self._semaphore.release()
            except Empty:
                if deadline and time.time() >= deadline:
                    raise Empty("Connection pool timeout")

    def release(self, conn):
        """Return a connection to the pool."""
        if conn is None or self._shutdown:
            return

        pooled_conn = PooledConnection.__new__(PooledConnection)
        pooled_conn.conn = conn

        # Check if connection is still usable
        try:
            if conn.is_open():
                # Preserve original creation time if we can find it, otherwise use now
                # (connection will be refreshed sooner, which is safe)
                pooled_conn.created_at = time.time()
                self._queue.put_nowait(pooled_conn)
                return
        except Exception:
            pass

        # Connection is dead, release semaphore slot
        self._semaphore.release()

    def release_pool(self):
        """Close all connections and shutdown the pool."""
        self._shutdown = True

        # Stop cleanup greenlet
        if self._cleanup_greenlet:
            self._cleanup_greenlet.kill()
            self._cleanup_greenlet = None

        # Close all queued connections
        while True:
            try:
                pooled_conn = self._queue.get_nowait()
                self._close_connection(pooled_conn)
            except Empty:
                break

        log.info("RethinkDB connection pool released")

    def _cleanup_loop(self):
        """Background greenlet that removes stale connections."""
        while not self._shutdown:
            gevent.sleep(self._cleanup_interval)
            if self._shutdown:
                break

            cleaned = 0
            valid_conns = []

            # Drain queue and check each connection
            while True:
                try:
                    pooled_conn = self._queue.get_nowait()
                    if self._is_valid(pooled_conn):
                        valid_conns.append(pooled_conn)
                    else:
                        self._close_connection(pooled_conn)
                        self._semaphore.release()
                        cleaned += 1
                except Empty:
                    break

            # Put valid connections back
            for pooled_conn in valid_conns:
                self._queue.put_nowait(pooled_conn)

            if cleaned > 0:
                log.debug(
                    f"Connection pool cleanup: removed {cleaned} stale connections"
                )


def init_pool(host, port, db, auth_key="", pool_size=32, conn_ttl=3600):
    """Initialize the global connection pool."""
    global _pool
    _pool = ConnectionPool(
        host=host,
        port=int(port),
        db=db,
        auth_key=auth_key,
        pool_size=pool_size,
        conn_ttl=conn_ttl,
    )
    log.info(
        f"RethinkDB connection pool initialized: {host}:{port}/{db} (pool_size={pool_size})"
    )
    return _pool


def get_pool():
    """Get the global connection pool."""
    global _pool
    return _pool


def release_pool():
    """Release all connections in the pool."""
    global _pool
    if _pool:
        _pool.release_pool()
        _pool = None


class RDB(object):
    """RethinkDB connection wrapper using connection pool."""

    def __init__(self, app=None, db=None):
        self.app = app
        self.db = db
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        @app.teardown_appcontext
        def teardown(exception):
            ctx = stack.top
            if hasattr(ctx, "rethinkdb"):
                conn = ctx.rethinkdb
                ctx.rethinkdb = None
                pool = get_pool()
                if pool and conn:
                    try:
                        pool.release(conn)
                    except Exception as e:
                        log.warning(f"Error releasing connection to pool: {e}")
                elif conn:
                    try:
                        conn.close()
                    except Exception:
                        pass

    def connect(self):
        """Create a direct connection (for backward compatibility)."""
        return r.connect(
            host=current_app.config["RETHINKDB_HOST"],
            port=current_app.config["RETHINKDB_PORT"],
            auth_key=current_app.config["RETHINKDB_AUTH"],
            db=self.db or current_app.config["RETHINKDB_DB"],
        )

    @property
    def conn(self):
        """Acquire a connection from the pool for the current request context."""
        ctx = stack.top
        if ctx is not None:
            if not hasattr(ctx, "rethinkdb") or ctx.rethinkdb is None:
                pool = get_pool()
                if pool:
                    try:
                        ctx.rethinkdb = pool.acquire(timeout=30)
                    except Empty:
                        log.error(
                            "RethinkDB connection pool exhausted after 30s timeout"
                        )
                        raise Error(
                            "service_unavailable",
                            "Database connection pool exhausted. Please try again.",
                            description_code="database_busy",
                        )
                else:
                    # Fallback to direct connection if pool not initialized
                    ctx.rethinkdb = self.connect()
            return ctx.rethinkdb
