#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2023 Simó Albert i Beltran
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

"""Pool-backed RethinkDB connection sharing for engine.

The legacy ``_ThreadLocalConnection`` descriptor handed every engine
worker thread a dedicated connection that the thread held forever
(reconnecting on socket close, never releasing). With 50+ long-lived
threads (DiskOperationsThread, ThreadHypEvents, manager_pooling, the
hypervisor workers) that pinned ~50 sockets to engine regardless of
activity, and a thread idle for 10 minutes between queries still
held its slot.

This module replaces the descriptor with a context-manager facade
identical in shape to ``_common``'s ``RethinkSharedConnection`` but
pointed at engine's ``ThreadSafeConnectionPool``. Each
``with cls._rdb_context()`` block acquires one connection from
the engine pool for the block's duration and releases it on exit;
threads that go quiet free their slot for the next caller.

The public contract callers depend on is unchanged:

    with cls._rdb_context():
        result = r.table(...).run(cls._rdb_connection)

``cls._rdb_connection`` is a per-thread descriptor (plus a metaclass
property for class-level reads), so the same syntax keeps working
without changes at any of the ``_common`` ORM model callsites that
inherit through ``rethink_custom_base_factory``.
"""

import os
import threading
from abc import ABC, ABCMeta

from isardvdi_common.connections.rethink_base import RethinkBase

from engine.services.db.db import connection_pool

# Bound on how long ``Context.__enter__`` may block waiting for a
# free pool slot. Mirrors the env var ``_common`` and ``engine.
# services.db.db`` already honour, so an operator only has to set
# it once. ``PoolExhaustedError`` (a ``ReqlDriverError`` subclass)
# is what the fork raises on timeout — engine's outer loops already
# catch ``ReqlDriverError`` for reconnect.
_ACQUIRE_TIMEOUT_S = float(os.environ.get("RETHINKDB_ACQUIRE_TIMEOUT_SEC", "30"))

# Per-thread storage for the connection currently checked out from the
# pool, plus a re-entrancy depth counter. Engine workers are sync
# threads (no asyncio), so ``threading.local`` is the right primitive
# — each worker thread sees its own ``conn``/``depth`` slot, and
# nested ``with cls._rdb_context()`` calls within a single thread
# reuse the outermost block's connection.
_thread_local = threading.local()


class Context:
    """Acquire one connection from the engine pool for the duration
    of a ``with`` block and release it back on exit.

    Re-entrant within a single thread: nested ``with cls._rdb_context()``
    blocks reuse the outermost block's connection (release happens
    only when the outermost block exits). This matches ``_common``'s
    ``RethinkSharedConnection.Context`` so engine and the rest of
    the monorepo share the same semantics.

    Concurrent threads each acquire a distinct connection from the
    pool. Up to ``RETHINKDB_POOL_SIZE`` queries (default 50 in
    engine) run truly in parallel.
    """

    def __enter__(self):
        depth = getattr(_thread_local, "depth", 0)
        if depth == 0:
            _thread_local.conn = connection_pool.acquire(timeout=_ACQUIRE_TIMEOUT_S)
        _thread_local.depth = depth + 1

    def __exit__(self, *args):
        _thread_local.depth = getattr(_thread_local, "depth", 1) - 1
        if _thread_local.depth == 0:
            conn = getattr(_thread_local, "conn", None)
            _thread_local.conn = None
            if conn is not None:
                connection_pool.release(conn)


class _PoolConnectionMeta(ABCMeta):
    """Metaclass that exposes ``_rdb_connection`` as a class-level
    property routing to the per-thread pool-acquired connection.

    Python only invokes class-level descriptors via the metaclass,
    not via descriptors in the class itself, so ``Cls._rdb_connection``
    (the form ``_common``'s ORM models use everywhere — see
    ``components/_common/src/isardvdi_common/models/*.py``) requires
    this metaclass property to function. Instance-level access
    (``self._rdb_connection``) is handled by the regular property
    on :class:`RethinkCustomBase`.

    Inheriting from :class:`ABCMeta` keeps :class:`RethinkCustomBase`
    compatible with :class:`abc.ABC` and the ``@abstractmethod``
    ``_rdb_connection`` declared on :class:`RethinkBase`.

    **Read fallback for tests.** Production code opens a
    :class:`Context` block which sets ``_thread_local.conn``
    directly, so reading ``cls._rdb_connection`` returns the
    pool-acquired connection on the calling thread. Tests typically
    bypass ``Context`` and inject a mock via ``monkeypatch.setattr(
    cls, "_rdb_connection", mock)``. That setattr goes through the
    setter below, which writes to a process-wide fallback
    ``_rdb_connection_override`` (in addition to the per-thread
    slot), so worker threads where ``_thread_local`` is empty pick
    it up via the getter's fallback.
    """

    @property
    def _rdb_connection(cls):
        local_conn = getattr(_thread_local, "conn", None)
        if local_conn is not None:
            return local_conn
        return getattr(cls, "_rdb_connection_override", None)

    @_rdb_connection.setter
    def _rdb_connection(cls, value):
        # Inside a ``with cls._rdb_context()`` block the per-thread
        # slot already holds the pool connection — keep it in sync.
        # Outside any block (test injection path), the fallback is
        # the only writable slot.
        _thread_local.conn = value
        type.__setattr__(cls, "_rdb_connection_override", value)


class RethinkCustomBase(RethinkBase, ABC, metaclass=_PoolConnectionMeta):
    """
    Manage Rethink Documents with engine's pool-backed connection.

    Open a ``_rdb_context`` block and use ``_rdb_connection`` to run
    queries — concurrent threads each get an independent pool-managed
    connection for the duration of their context block.

    Use the constructor with keyword arguments to create new Rethink
    Documents or update an existing one using the id keyword. Use the
    constructor with id as the first argument to create an object
    representing an existing Rethink Document.
    """

    _rdb_context = Context
    # Test-injection fallback (see the metaclass docstring).
    # Production never reads this — ``Context`` populates
    # ``_thread_local`` first and the getter prefers that.
    _rdb_connection_override = None

    @property
    def _rdb_connection(self):
        """Instance-level access (``self._rdb_connection``) mirrors
        the metaclass property: per-thread first, fallback second.
        Without this the abstract ``_rdb_connection`` declared in
        :class:`RethinkBase` would never be satisfied and
        instantiating subclasses would raise ``TypeError: Can't
        instantiate abstract class``.
        """
        local_conn = getattr(_thread_local, "conn", None)
        if local_conn is not None:
            return local_conn
        return type(self)._rdb_connection_override

    @_rdb_connection.setter
    def _rdb_connection(self, value):
        _thread_local.conn = value
        type(self)._rdb_connection_override = value
