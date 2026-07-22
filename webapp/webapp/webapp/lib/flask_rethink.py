#
#   Copyright © 2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
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

"""Flask extension that proxies ``g.rethinkdb`` / ``db.conn`` through
``isardvdi_common``'s shared ``ThreadSafeConnectionPool`` instead of
opening a fresh socket per Flask request.

The legacy implementation called ``r.connect(...)`` on every first
``db.conn`` access in a request, then ``conn.close()`` at teardown.
That's a TCP open + RethinkDB handshake per request — unnecessary
overhead, and uncapped: under load the webapp could open arbitrarily
many connections and exhaust the rdb server's connection budget
(empirically capped around 50).

The pool already lives in ``isardvdi_common.connections.
rethink_shared_connection``: every other Python service in the
monorepo (apiv4, change-handler, changefeed, scheduler, ...) acquires
through it. Routing webapp's per-request connections through the
same pool: caps the connection count to ``RETHINKDB_POOL_SIZE``,
removes per-request socket churn, and lights up the slow-/failed-
query observer (P2.1) for every webapp query without further work.

Today no Flask handler outside ``tests/`` consumes ``g.rethinkdb`` —
the active request paths use ``isardvdi_common``'s ``RethinkSharedConnection``
classmethods directly. This rewrite is therefore defensive: if any
future code adds ``db.conn`` calls (or revives one of the dormant
import sites), it lands on the pool by default.
"""

import logging as log

from flask import current_app, g
from isardvdi_common.connections.rethink_shared_connection import (
    Context as _PoolContext,
)
from isardvdi_common.connections.rethink_shared_connection import _thread_local
from rethinkdb import RethinkDB

# Re-exported for callers that historically did ``from
# webapp.lib.flask_rethink import r``. The pool owns connection
# lifecycle — never call ``r.connect(...)`` against this object.
r = RethinkDB()


class RDB(object):
    """Flask extension that hands out shared-pool connections.

    The legacy constructor accepted a ``db`` kwarg to override the
    default database; the pool is process-global to ``RETHINKDB_DB``,
    so a non-default ``db`` argument is not supported on the pool
    path. The kwarg is preserved for source compatibility but raises
    if it would change the connected DB at acquire time.
    """

    def __init__(self, app=None, db=None):
        self.app = app
        self.db = db
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        @app.teardown_appcontext
        def teardown(exception):
            ctx = g.pop("rethinkdb_pool_ctx", None)
            g.pop("rethinkdb", None)
            if ctx is not None:
                try:
                    ctx.__exit__(None, None, None)
                except Exception:
                    # The Flask app-context teardown chain must not be
                    # interrupted by a pool release error; surface it
                    # as a log line and keep going.
                    log.exception(
                        "Failed to release rdb pool connection at request teardown"
                    )

    @property
    def conn(self):
        """Return the per-request rdb connection.

        First access in a Flask app context acquires from
        ``isardvdi_common``'s ``ThreadSafeConnectionPool`` and stashes
        the context manager on ``g`` so the matching release happens
        at ``teardown_appcontext`` time. Subsequent accesses in the
        same context return the cached connection.

        If the caller passed a non-default ``db`` to the constructor
        and it differs from ``RETHINKDB_DB``, raise — the pool always
        targets ``RETHINKDB_DB``.
        """
        if "rethinkdb" not in g:
            override_db = self.db
            if override_db is not None:
                configured = current_app.config.get("RETHINKDB_DB")
                if override_db != configured:
                    raise RuntimeError(
                        f"RDB(db={override_db!r}) does not match the pool's "
                        f"RETHINKDB_DB={configured!r}; per-instance database "
                        "overrides are not supported on the pool path"
                    )
            ctx = _PoolContext()
            ctx.__enter__()
            # ``Context.__enter__`` populated the per-thread connection
            # slot. Stash both the context (for clean teardown) and the
            # connection itself (the legacy g.rethinkdb contract).
            g.rethinkdb_pool_ctx = ctx
            g.rethinkdb = _thread_local.conn
        return g.rethinkdb
