# SPDX-License-Identifier: AGPL-3.0-or-later
"""Pooled rethinkdb connection for the VPN service.

Replaces the legacy ``r.connect(...).repl()`` pattern in ``wgadmin.py``
with a per-call acquire from ``isardvdi_common``'s
``ThreadSafeConnectionPool``. The .repl() global was deprecated by the
rdb driver and unsafe under multi-threaded use; this module gives every
``r.table(...).run(conn)`` callsite an explicit, pool-managed connection.

Usage:

    from db import vpn_rethink_conn

    with vpn_rethink_conn() as conn:
        result = r.table("users").get(user_id).run(conn)

Connections are released back to the pool on context exit. Re-entrant
within a single thread (a nested ``with vpn_rethink_conn():`` reuses
the outer connection — the underlying ``Context`` keeps a depth
counter). Concurrent threads each get their own connection. Slow- and
failed-query telemetry (P2.1) is wired automatically because the pool
factory in ``_common`` registers the observer on every connection.
"""

from __future__ import annotations

from isardvdi_common.connections import rethink_shared_connection as _rsc


class vpn_rethink_conn:  # noqa: N801 — keep snake_case for usage clarity at callsites
    """Context manager yielding a connection from ``_common``'s pool.

    The pool already knows how to read ``RETHINKDB_HOST`` / ``PORT`` /
    ``DB`` / ``AUTH`` from the environment and has the slow-query
    observer wired in, so this class is a thin shim that exposes the
    acquired connection as the context value.
    """

    def __enter__(self):
        self._ctx = _rsc.Context()
        self._ctx.__enter__()
        return _rsc._thread_local.conn

    def __exit__(self, exc_type, exc, tb):
        return self._ctx.__exit__(exc_type, exc, tb)
