#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2023,2025 Simó Albert i Beltran
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pool-backed RethinkDB connection sharing.

The legacy implementation maintained a single process-wide connection
that ``Context.__enter__`` would (re)open and ``Context.__exit__``
would close. Two latent problems with that pattern:

1. **Concurrency hazard.** ``cls._rdb_connection`` was a plain class
   attribute. Two concurrent callers each entering their own
   ``with cls._rdb_context()`` block would clobber each other's
   connection assignment, and one's ``Context.__exit__`` would close
   the connection the other was still using mid-query.

2. **Throughput ceiling.** A single connection serialises every query
   through the driver's per-connection write lock, so ``asyncio.to_thread``
   tasks fanning out across worker threads still queued behind one
   socket. Bulk operations (e.g. a 22-desktop deployment) were
   pinned to roughly ``1 / single-query-latency`` queries per second.

This module replaces the singleton with a
:class:`rethinkdb.connection_pool.ThreadSafeConnectionPool` from the
``isard-vdi/rethinkdb-python`` fork. Each ``with cls._rdb_context()``
block acquires one connection from the pool for the duration of the
block and releases it on exit. Concurrent callers each get a
distinct connection, so up to ``RETHINKDB_POOL_SIZE`` queries (default
``10``) can run truly in parallel.

The public contract that 1,200+ callers rely on is unchanged:

    with cls._rdb_context():
        result = r.table(...).run(cls._rdb_connection)

``cls._rdb_connection`` is implemented as a thread-local descriptor
(plus a metaclass property for the rare ``ClassName._rdb_connection``
class-level read), so the same syntax keeps working without any
changes at the call site. Outside an active ``with`` block the
attribute reads as ``None`` — this is a behaviour change from the
legacy code which would return a possibly-stale closed connection
from the previous block. Every existing caller is inside a context
block (verified by grep), so no breakage in practice.
"""

import logging
import threading
from abc import ABC, ABCMeta
from os import environ
from typing import Optional

from isardvdi_common.helpers.atexit_register import atexit_register
from rethinkdb import r
from rethinkdb.connection_pool import PoolExhaustedError, ThreadSafeConnectionPool
from rethinkdb.net import Connection, Query

# Bound on how long ``Context.__enter__`` may block waiting for a free
# pool slot. Without a finite timeout an exhausted pool wedges the
# calling worker thread indefinitely; with one, the fork raises
# ``PoolExhaustedError`` (a ``ReqlDriverError`` subclass) which the
# apiv4 exception handler maps to a 503. The default sits well above
# the observed worst-case query duration so it never trips on a
# healthy pool, only on real saturation. Override via
# ``RETHINKDB_ACQUIRE_TIMEOUT_SEC`` on the service container.
_ACQUIRE_TIMEOUT_S = float(environ.get("RETHINKDB_ACQUIRE_TIMEOUT_SEC", "30"))

# Slow-query telemetry. Default 500ms — every query taking longer
# than this emits a single ``rdb_query_slow`` log line; failed
# queries always log as ``rdb_query_failed`` regardless of duration.
# Override via ``RETHINKDB_SLOW_QUERY_MS`` env var on the service
# container.
_SLOW_QUERY_S = float(environ.get("RETHINKDB_SLOW_QUERY_MS", "500")) / 1000.0
_query_log = logging.getLogger("rdb.query")


def _summarize_query(query: Optional[Query]) -> str:
    """Render a short PII-bounded summary of a Query's term AST.

    The repr of a ReQL term is structural — it shows
    ``r.table('users').get('<id>').pluck('a','b')`` or similar; the
    table/field names and any literal id are visible but no row data
    is ever serialized into the query AST itself, so this stays
    safe-by-default for log shipping. Truncated to 200 chars to bound
    log volume on long batched expressions.
    """
    if query is None or query.term is None:
        return f"<query type={getattr(query, 'type', '?')}>"
    try:
        rendered = repr(query.term)
    except Exception:
        rendered = "<unrepresentable>"
    return rendered[:200]


def _pool_stats_extra(pool=None) -> dict:
    """Snapshot a pool's size / in_use / idle for log enrichment.

    Reads are racy by design — these are diagnostic fields, not
    invariants — so we don't bother with locking.

    ``pool`` defaults to the module-scoped shared pool; engine has
    its own ``ThreadSafeConnectionPool`` instance distinct from
    `_common`'s and passes it explicitly via
    :func:`make_query_observer`. Returns an empty dict when no pool
    is reachable (test contexts, dedicated-connection callers in
    services that never touched any pool). Empty merges cleanly
    into the log ``extra`` so callers don't have to branch.
    """
    pool = pool if pool is not None else _pool
    if pool is None:
        return {}
    try:
        return {
            "pool_size": pool.size,
            "pool_in_use": pool.in_use,
            "pool_idle": pool.idle,
            "pool_max_size": pool.max_size,
        }
    except Exception:
        # If the pool is partway through close() the properties may
        # transiently raise. Drop the enrichment rather than break
        # the observer call — a slow-query line without pool stats
        # is still useful.
        return {}


def make_query_observer(pool=None):
    """Return a per-query telemetry observer bound to ``pool``.

    Engine maintains its own ``ThreadSafeConnectionPool`` (see
    ``engine/services/db/db.py``) distinct from `_common`'s shared
    pool. Calling ``make_query_observer(engine_pool)`` returns an
    observer whose emitted ``rdb_query_slow`` / ``rdb_query_failed``
    lines carry the *engine* pool's size / in_use / idle / max_size
    instead of `_common`'s — without the engine factory needing to
    duplicate the observer's logging logic.

    ``pool=None`` (the default) keeps the legacy `_common` behaviour:
    pool stats come from the module-scoped shared pool. Use that for
    callers attaching the observer to dedicated (non-pooled)
    connections too — the enrichment will simply be empty since the
    shared pool is uninvolved.
    """

    def _observer(
        query: Query, duration_s: float, exception: Optional[BaseException]
    ) -> None:
        # Hooks run synchronously on the rdb network thread; keep
        # them cheap. The driver (commit ``2564aab`` on the modernize
        # branch) snapshots its observer list before firing, so it's
        # safe to add this once per pooled connection and leave it.
        duration_ms = round(duration_s * 1000.0, 2)
        if exception is not None:
            _query_log.warning(
                "rdb_query_failed",
                extra={
                    "query": _summarize_query(query),
                    "duration_ms": duration_ms,
                    "error_type": type(exception).__name__,
                    "error_msg": str(exception)[:200],
                    **_pool_stats_extra(pool),
                },
            )
            return
        if duration_s >= _SLOW_QUERY_S:
            _query_log.warning(
                "rdb_query_slow",
                extra={
                    "query": _summarize_query(query),
                    "duration_ms": duration_ms,
                    **_pool_stats_extra(pool),
                },
            )

    return _observer


# Default observer bound to the shared `_common` pool — preserved as
# a module-level attribute so existing imports
# (``from isardvdi_common.connections.rethink_shared_connection import
# _query_observer_on_end``) keep working unchanged. Used by the
# dedicated-connection helper (``rethink_dedicated_connection.py``)
# and historically by every Tier-1/3/4 service that consumes the
# shared pool.
_query_observer_on_end = make_query_observer()


# Per-thread storage for the connection currently checked out from the
# pool, plus a re-entrancy depth counter. ``threading.local`` was chosen
# over ``contextvars.ContextVar`` because every existing call site uses
# the sync rethinkdb driver — asyncio code that needs concurrency goes
# through ``asyncio.to_thread`` which spawns worker threads. If/when
# the codebase migrates to native asyncio rethinkdb (Phase 2 in the
# RethinkDB driver evaluation) the storage can switch to
# ``ContextVar`` without touching any caller.
_thread_local = threading.local()

_pool: Optional[ThreadSafeConnectionPool] = None
_pool_lock = threading.Lock()


def _connection_factory() -> Connection:
    """Build a fresh blocking RethinkDB connection. Used by the pool
    to top up to ``max_size`` on demand.

    Each connection is wired with a slow/failed-query observer so the
    pool emits structured log lines when individual queries breach
    the threshold. The observer is registered once per connection at
    creation and lives for the lifetime of the connection in the
    pool.
    """
    conn = r.connect(
        host=environ.get("RETHINKDB_HOST", "isard-db"),
        port=int(environ.get("RETHINKDB_PORT", "28015")),
        auth_key=environ.get("RETHINKDB_AUTH", ""),
        db=environ.get("RETHINKDB_DB", "isard"),
    )
    conn.add_query_observer(on_end=_query_observer_on_end)
    return conn


def _get_pool() -> ThreadSafeConnectionPool:
    """Return the lazily-created module-scoped pool. Lazy creation
    avoids opening connections at import time so that test contexts
    (which patch ``r.connect``) can do so before any code path
    touches the database."""
    global _pool
    if _pool is None:
        with _pool_lock:
            if _pool is None:
                _pool = ThreadSafeConnectionPool(
                    connection_factory=_connection_factory,
                    max_size=int(environ.get("RETHINKDB_POOL_SIZE", "10")),
                    max_idle_time=float(environ.get("RETHINKDB_POOL_IDLE_SEC", "300")),
                )
    return _pool


def _set_pool_for_tests(pool: Optional[ThreadSafeConnectionPool]) -> None:
    """Test-only seam. Production code MUST NOT call this — it lets
    unit tests inject a mock pool without monkey-patching the
    module's private state directly."""
    global _pool
    _pool = pool


class Context:
    """Acquire one connection from the shared pool for the duration of
    a ``with`` block and release it back on exit.

    Re-entrant within a single thread: nested ``with cls._rdb_context()``
    blocks reuse the outermost block's connection (release happens
    only when the outermost block exits). This matches the legacy
    behaviour where the singleton was kept alive across nested calls.

    Concurrent callers (other threads, or asyncio tasks running on
    worker threads via ``asyncio.to_thread``) each acquire a distinct
    connection from the pool. Up to ``RETHINKDB_POOL_SIZE`` queries
    run truly in parallel — the entire point of this rewrite.
    """

    def __enter__(self):
        depth = getattr(_thread_local, "depth", 0)
        if depth == 0:
            # Acquire a fresh connection from the pool. The pool's
            # ``acquire`` validates ``is_open()`` and evicts stale
            # connections automatically — no manual reconnect logic
            # needed here, unlike the legacy ``Context``. A finite
            # timeout converts pool exhaustion into a fast
            # ``PoolExhaustedError`` (mapped to 503 in apiv4) instead
            # of wedging the worker thread until the caller's
            # request timeout fires.
            _thread_local.conn = _get_pool().acquire(timeout=_ACQUIRE_TIMEOUT_S)
        _thread_local.depth = depth + 1

    def __exit__(self, *args):
        _thread_local.depth = getattr(_thread_local, "depth", 1) - 1
        if _thread_local.depth == 0:
            conn = getattr(_thread_local, "conn", None)
            _thread_local.conn = None
            if conn is not None:
                _get_pool().release(conn)


class _PoolConnectionMeta(ABCMeta):
    """Metaclass that exposes ``_rdb_connection`` as a class-level
    property routing to the per-thread pool-acquired connection.

    Python only invokes class-level descriptors via the *metaclass*,
    not via descriptors in the class itself, so ``Cls._rdb_connection``
    requires this metaclass property to function. Instance-level
    access (``self._rdb_connection``) is handled by the regular
    property defined on :class:`RethinkSharedConnection` below.

    Inheriting from :class:`ABCMeta` keeps ``RethinkSharedConnection``
    compatible with :class:`abc.ABC` and the rest of the
    abstract-class machinery used elsewhere (notably
    :class:`RethinkBase` whose abstract ``_rdb_connection`` property
    this concretely implements).

    **Read fallback for tests.** Production code opens a
    :class:`Context` block which sets ``_thread_local.conn`` directly,
    so reading ``cls._rdb_connection`` returns the pool-acquired
    connection on the calling thread. Tests typically *bypass*
    ``Context`` (the apiv4 conftest monkey-patches ``_rdb_context`` to
    :class:`contextlib.nullcontext`) and inject a mock connection via
    ``monkeypatch.setattr(cls, "_rdb_connection", mock)``. That setattr
    goes through the setter below, which writes to a process-wide
    fallback (in addition to the per-thread slot) so that
    ``await asyncio.to_thread(sync_helper)`` — where the worker
    thread's ``_thread_local`` is empty — still resolves to the
    test's mock instead of ``None``. Production never relies on the
    fallback because ``Context.__enter__`` always populates the
    per-thread slot first.
    """

    @property
    def _rdb_connection(cls):
        local_conn = getattr(_thread_local, "conn", None)
        if local_conn is not None:
            return local_conn
        # Fall back to the test-only override (or ``None`` in
        # production where Context populates ``_thread_local`` and
        # the fallback is never set).
        return getattr(cls, "_rdb_connection_override", None)

    @_rdb_connection.setter
    def _rdb_connection(cls, value):
        # Inside a ``with cls._rdb_context()`` block the per-thread
        # slot already holds the pool connection — keep it in sync.
        # Outside any block (test injection path), the fallback is
        # the only writable slot; the worker-thread reader of an
        # ``asyncio.to_thread``-offloaded handler picks it up via
        # the getter's fallback.
        _thread_local.conn = value
        type.__setattr__(cls, "_rdb_connection_override", value)


class RethinkSharedConnection(ABC, metaclass=_PoolConnectionMeta):
    """
    Pool-backed shared-connection facade.

    Open ``_rdb_context`` and use ``_rdb_connection`` to run queries.
    Concurrent callers each get an independent pool-managed connection
    for the duration of their context block.
    """

    _rdb_context = Context
    # Test-injection fallback (see the metaclass docstring). Production
    # never reads this — ``Context`` populates ``_thread_local`` first
    # and the metaclass getter prefers that.
    _rdb_connection_override = None

    @property
    def _rdb_connection(self):
        """Instance-level access (``self._rdb_connection``) mirrors
        the metaclass property: per-thread first, fallback second.
        Without this property the abstract ``_rdb_connection``
        declared in :class:`RethinkBase` would never be satisfied
        and instantiating subclasses like
        :class:`RethinkCustomBase` would raise ``TypeError: Can't
        instantiate abstract class``."""
        local_conn = getattr(_thread_local, "conn", None)
        if local_conn is not None:
            return local_conn
        return type(self)._rdb_connection_override

    @_rdb_connection.setter
    def _rdb_connection(self, value):
        _thread_local.conn = value
        type(self)._rdb_connection_override = value

    @classmethod
    @atexit_register
    def _rethink_disconnect(cls):
        """Close the entire pool at process shutdown. Replaces the
        legacy ``cls._rdb_connection.close()`` which used to run
        against the singleton — meaningless against a pool."""
        global _pool
        if _pool is not None:
            try:
                _pool.close()
            except Exception:
                # Process is exiting; swallow secondary errors so the
                # registered ``atexit`` chain doesn't get interrupted.
                pass
            _pool = None
