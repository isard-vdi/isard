#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""apiv4 startup runs its database work off the event loop thread, in order,
and finishes it before serving."""

import asyncio
import threading
from unittest.mock import AsyncMock, MagicMock

import api
from fastapi import FastAPI


def test_startup_database_work_runs_off_the_loop_before_serving(monkeypatch):
    calls = []

    def recorder(name):
        return lambda *a, **kw: calls.append((name, threading.get_ident()))

    monkeypatch.setattr(api, "_wire_grpc_providers", lambda: None)
    monkeypatch.setattr(
        "isardvdi_common.connections.rethink_shared_connection.warm_pool",
        lambda: None,
    )
    monkeypatch.setattr(
        api.Maintenance, "initialization", recorder("maintenance"), raising=False
    )
    monkeypatch.setattr(api.Cards, "seed_stock_cards", recorder("seed_cards"))
    monkeypatch.setattr(api.Cards, "cleanup_missing", recorder("cleanup_cards"))
    monkeypatch.setattr(api, "_sync_haproxy_maps", recorder("haproxy_maps"))
    monkeypatch.setattr(
        "api.connections.grpc_client.create_resync_watch_channel",
        MagicMock(side_effect=RuntimeError("no haproxy in tests")),
    )
    queue = MagicMock(initialize=AsyncMock(), start=AsyncMock(), stop=AsyncMock())
    monkeypatch.setattr(api, "RecycleBinDeleteQueue", lambda: queue)

    async def main():
        loop_thread = threading.get_ident()
        async with api.lifespan(FastAPI()):
            serving = list(calls)
        return loop_thread, serving

    loop_thread, serving = asyncio.run(main())

    assert [name for name, _ in serving] == [
        "maintenance",
        "seed_cards",
        "cleanup_cards",
        "haproxy_maps",
    ]
    assert all(t != loop_thread for _, t in serving), serving
