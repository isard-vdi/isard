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
"""

from os import environ

from isardvdi_common.connections.rethink_shared_connection import _query_observer_on_end
from rethinkdb import r
from rethinkdb.net import Connection


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
