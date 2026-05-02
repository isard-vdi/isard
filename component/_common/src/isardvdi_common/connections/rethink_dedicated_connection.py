#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 Simó Albert i Beltran
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

"""Dedicated (non-pooled) RethinkDB connection.

Use this for long-held cursors (changefeeds, ``.changes()``) and any
work that would otherwise occupy a shared-pool slot for the lifetime
of the process. A 4-slot pool with one cursor pinned permanently has
already lost 25% of its capacity to a single workload.

The returned connection is wired with the same slow-/failed-query
observer as pool connections (P2.1 telemetry), so dedicated-connection
queries surface in the same ``rdb_query_slow`` / ``rdb_query_failed``
log stream consumers already grep for.

Lifecycle ownership lives with the caller — close the connection
(``conn.close()``) when the cursor is torn down. The pool's
``Context.__enter__/__exit__`` machinery does NOT manage these
connections; that is the entire point.

Use cases:

- ``isardvdi_changefeed.TableChangefeed.run`` — one cursor that
  multiplexes every watched table's ``.changes()`` stream into Redis
  for the process lifetime. Holding a pool slot here defeats the pool.
- A future startup-only readiness probe that wants its own short-lived
  socket without contending with the active request mix.

Anything short-lived — request-scoped queries, classmethod helpers,
isardvdi_common methods — should keep using
``RethinkSharedConnection._rdb_context()``: the shared pool is more
efficient for ad-hoc work.

Two flavours:

- :func:`dedicated_connection` — sync (blocking) connection. The
  cursor's ``for change in cursor:`` blocks the calling thread on
  socket recv between deliveries. Use from sync code or from
  asyncio with ``asyncio.to_thread`` if the iteration must not
  freeze the event loop.
- :func:`dedicated_async_connection` — asyncio-native connection
  (P2 #10, 2026-05-02). Returns a connection whose
  ``await query.run(conn)`` produces an :class:`AsyncioCursor`
  that supports ``async for change in cursor:``. The asyncio event
  loop schedules other tasks while the cursor waits on socket
  recv — no worker thread / asyncio.Queue plumbing required.
"""

import threading
from os import environ
from typing import TYPE_CHECKING, Any

from isardvdi_common.connections.rethink_shared_connection import _query_observer_on_end
from rethinkdb import r
from rethinkdb.net import Connection

if TYPE_CHECKING:
    # Only imported for type hints — avoids the import-time cost of
    # the asyncio backend in services that never touch it.
    from rethinkdb.asyncio_net.net_asyncio import Connection as AsyncioConnection


def dedicated_connection() -> Connection:
    """Open a fresh blocking RethinkDB connection bypassing the pool.

    Wires the slow-/failed-query observer used by pool connections so
    every dedicated-connection query also flows into the
    ``rdb.query`` logger. Connection parameters mirror
    ``rethink_shared_connection._connection_factory`` so dedicated
    connections land on the same database the pool uses.

    The caller MUST close the returned connection (or use it as a
    context manager) when finished — the pool will not.
    """
    conn = r.connect(
        host=environ.get("RETHINKDB_HOST", "isard-db"),
        port=int(environ.get("RETHINKDB_PORT", "28015")),
        auth_key=environ.get("RETHINKDB_AUTH", ""),
        db=environ.get("RETHINKDB_DB", "isard"),
    )
    conn.add_query_observer(on_end=_query_observer_on_end)
    return conn


# Module-scoped :class:`RethinkDB` instance with the asyncio loop type
# wired. Created lazily on first use so import-time test contexts
# (which stub the ``rethinkdb`` module) don't trip on the
# ``set_loop_type`` call. Kept separate from the global ``r`` so
# services that mix async (cursor) + sync (pool) paths — i.e.
# changefeed — don't accidentally turn the global ``r`` async and
# break the shared pool's ``_connection_factory``.
_r_async: Any = None
_r_async_lock = threading.Lock()


def _get_r_async():
    """Lazy-build the asyncio :class:`RethinkDB` instance."""
    global _r_async
    if _r_async is None:
        with _r_async_lock:
            if _r_async is None:
                from rethinkdb import RethinkDB

                instance = RethinkDB()
                instance.set_loop_type("asyncio")
                _r_async = instance
    return _r_async


async def dedicated_async_connection() -> "AsyncioConnection":
    """Open a fresh asyncio-native RethinkDB connection bypassing every
    pool.

    Counterpart to :func:`dedicated_connection` for callers running on
    an asyncio event loop. The returned connection's
    ``await query.run(conn)`` produces an
    :class:`rethinkdb.asyncio_net.net_asyncio.AsyncioCursor` that
    supports ``async for change in cursor:`` — the cursor's socket
    recv yields the loop between deliveries, so other coroutines on
    the same loop keep getting scheduled. Replaces the worker-thread
    + ``asyncio.Queue`` offload pattern :mod:`isardvdi_changefeed`
    used between P2 #8 and P2 #10.

    The same slow-/failed-query observer wires up: the fork's
    :meth:`Connection.add_query_observer` works against async
    connections via the coroutine-aware ``_run_query_observed`` path
    (see ``/opt/rethinkdb-python/rethinkdb/net.py`` ``_awaited``
    closure), so async-cursor open events still emit ``rdb_query_slow``
    when they breach the threshold. Note: the observer's
    ``duration`` for cursor-returning queries is the time-to-first-
    batch only; subsequent ``CONTINUE`` traffic is not reported.

    Caller MUST ``await conn.close(noreply_wait=False)`` (or use it as
    an ``async with`` context) when the cursor is torn down — there
    is no pool to clean up after them.
    """
    ra = _get_r_async()
    conn = await ra.connect(
        host=environ.get("RETHINKDB_HOST", "isard-db"),
        port=int(environ.get("RETHINKDB_PORT", "28015")),
        auth_key=environ.get("RETHINKDB_AUTH", ""),
        db=environ.get("RETHINKDB_DB", "isard"),
    )
    conn.add_query_observer(on_end=_query_observer_on_end)
    return conn
