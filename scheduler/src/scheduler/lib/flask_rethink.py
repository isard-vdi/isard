#
#   Copyright © 2022 Josep Maria Viñolas Auquer
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
``isardvdi_common``'s shared ``ThreadSafeConnectionPool``.

The legacy implementation called ``r.connect(...)`` on every first
``db.conn`` access in a Flask app context, then ``conn.close()`` at
teardown. APScheduler's ``Scheduler.__init__`` makes 8+ such calls
during startup (default-job seeding) and several per
``add_job``/``remove_job`` call thereafter. Each one was an open
TCP socket plus a RethinkDB handshake.

Routing through ``isardvdi_common``'s pool: caps the per-process
connection count to ``RETHINKDB_POOL_SIZE``, removes per-call
socket churn, and surfaces queries through the slow-/failed-query
observer (P2.1).

The ``RethinkDBJobStore`` (instantiated separately in
``Scheduler.__init__``) keeps its own dedicated rdb connection per
the APScheduler contract and is intentionally NOT routed through
this pool — APScheduler expects sole ownership of the jobstore
connection.
"""

import logging as log

from flask import current_app, g
from isardvdi_common.connections.rethink_shared_connection import (
    Context as _PoolContext,
)
from isardvdi_common.connections.rethink_shared_connection import _thread_local
from rethinkdb import RethinkDB

# Re-exported for callers that historically did ``from
# scheduler.lib.flask_rethink import r``. The pool owns connection
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
                    log.exception(
                        "Failed to release rdb pool connection at app-context teardown"
                    )

    @property
    def conn(self):
        """Return the per-context rdb connection.

        First access in a Flask app context acquires from
        ``isardvdi_common``'s ``ThreadSafeConnectionPool`` and stashes
        the context manager on ``g`` so the matching release happens
        at ``teardown_appcontext`` time. Subsequent accesses in the
        same context return the cached connection.

        Scheduler callers wrap their queries in
        ``with app.app_context(): r.table(...).run(db.conn)``;
        each ``with app.app_context()`` exits its own teardown which
        releases the pool slot. The hot-loop in APScheduler that
        fires jobstore queries keeps its own connection (see
        ``Scheduler.__init__`` and the ``RethinkDBJobStore``).
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
            g.rethinkdb_pool_ctx = ctx
            g.rethinkdb = _thread_local.conn
        return g.rethinkdb
