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

import threading
from abc import ABC, ABCMeta
from os import environ
from typing import Optional

from isardvdi_common.helpers.atexit_register import atexit_register
from rethinkdb import r
from rethinkdb.connection_pool import ThreadSafeConnectionPool
from rethinkdb.net import Connection

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
    to top up to ``max_size`` on demand."""
    return r.connect(
        host=environ.get("RETHINKDB_HOST", "isard-db"),
        port=int(environ.get("RETHINKDB_PORT", "28015")),
        auth_key=environ.get("RETHINKDB_AUTH", ""),
        db=environ.get("RETHINKDB_DB", "isard"),
    )


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
            # needed here, unlike the legacy ``Context``.
            _thread_local.conn = _get_pool().acquire()
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
