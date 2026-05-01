# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pin the dedicated (non-pooled) connection helper's contract.

What we want to guarantee:

1. Every call returns a *fresh* connection (not a pool acquire) — the
   helper is for long-held cursors that must not occupy a pool slot.
2. The returned connection has the slow-/failed-query observer
   wired in, so dedicated-connection traffic shows up in the same
   ``rdb.query`` stream as pool traffic (P2.1 telemetry contract).
3. Connection parameters (host/port/auth/db) come from environment
   variables, matching ``_connection_factory`` so both connection
   kinds land on the same database.
4. The caller — not the helper — owns lifecycle; the helper does not
   register a teardown atexit hook.
"""

from unittest.mock import MagicMock

import pytest


@pytest.fixture
def env(monkeypatch):
    """Lock down the environment so connect() is called with known args."""
    monkeypatch.setenv("RETHINKDB_HOST", "rdb-host")
    monkeypatch.setenv("RETHINKDB_PORT", "12345")
    monkeypatch.setenv("RETHINKDB_AUTH", "shh")
    monkeypatch.setenv("RETHINKDB_DB", "isard-test")


@pytest.fixture
def stubbed_connect(monkeypatch):
    """Patch ``r.connect`` on the dedicated module so no socket opens."""
    from isardvdi_common.connections import rethink_dedicated_connection as mod

    fake_r = MagicMock()
    fake_r.connect.side_effect = lambda **kwargs: MagicMock(name="dedicated-conn")
    monkeypatch.setattr(mod, "r", fake_r)
    return fake_r


def test_returns_fresh_connection_each_call(env, stubbed_connect):
    """The helper is the *opposite* of pool-acquire: every call must
    open a new connection, never recycle a previous one. Pinning this
    catches future regressions where someone "optimises" by adding a
    module-level cache."""
    from isardvdi_common.connections.rethink_dedicated_connection import (
        dedicated_connection,
    )

    a = dedicated_connection()
    b = dedicated_connection()

    assert a is not b, "dedicated_connection must return a new conn each call"
    assert stubbed_connect.connect.call_count == 2


def test_observer_is_wired(env, stubbed_connect):
    """Slow-query telemetry must reach dedicated connections too —
    otherwise a stuck changefeed cursor's ``rdb_query_failed`` lines
    won't surface in Loki."""
    from isardvdi_common.connections.rethink_dedicated_connection import (
        dedicated_connection,
    )
    from isardvdi_common.connections.rethink_shared_connection import (
        _query_observer_on_end,
    )

    conn = dedicated_connection()

    conn.add_query_observer.assert_called_once_with(on_end=_query_observer_on_end)


def test_connection_params_come_from_env(env, stubbed_connect):
    """Host/port/auth/db must come from the same env vars the pool
    factory reads. If they drift, dedicated connections silently land
    on a different database than the rest of the service."""
    from isardvdi_common.connections.rethink_dedicated_connection import (
        dedicated_connection,
    )

    dedicated_connection()

    stubbed_connect.connect.assert_called_once_with(
        host="rdb-host",
        port=12345,
        auth_key="shh",
        db="isard-test",
    )


def test_no_atexit_registration(env, stubbed_connect, monkeypatch):
    """The helper must not register process-shutdown teardown. Lifetime
    ownership belongs to the caller (changefeed loop, etc.), not to a
    library hook; otherwise teardown order across unrelated callers
    becomes a debugging black hole."""
    import atexit

    from isardvdi_common.connections import rethink_dedicated_connection as mod

    register_calls = []
    monkeypatch.setattr(
        atexit, "register", lambda *args, **kw: register_calls.append((args, kw))
    )
    monkeypatch.setattr(
        mod, "r", stubbed_connect
    )  # keep our stub after the atexit patch

    mod.dedicated_connection()

    assert register_calls == [], "dedicated_connection must not register atexit hooks"
