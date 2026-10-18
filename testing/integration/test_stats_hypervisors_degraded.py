# SPDX-License-Identifier: AGPL-3.0-or-later

"""The hypervisor stats inventory carries the engine's degraded state."""

from __future__ import annotations

import os
import time
import uuid

import pytest

rethinkdb = pytest.importorskip("rethinkdb")
from rethinkdb import r  # noqa: E402

STATS_URL = "/api/v4/admin/items/stats/hypervisors"
# the inventory is cached for the collector's scrape interval and served stale while it refreshes
CACHE_WAIT_S = 120


def _connect():
    host = os.environ.get("RETHINKDB_HOST", "isard-db")
    port = int(os.environ.get("RETHINKDB_PORT", "28015"))
    db = os.environ.get("RETHINKDB_DB", "isard")
    try:
        return r.connect(host=host, port=port, db=db)
    except Exception as exc:  # pragma: no cover - environment guard
        pytest.skip(f"RethinkDB not reachable at {host}:{port}: {exc}")


def _hypervisor(hyp_id, degraded):
    return {
        "id": hyp_id,
        "hostname": hyp_id,
        "status": "Offline",
        "enabled": False,
        "only_forced": True,
        "degraded": degraded,
    }


def _rows_for(admin_client, ids):
    deadline = time.monotonic() + CACHE_WAIT_S
    while True:
        rows = {row["id"]: row for row in admin_client.get(STATS_URL)}
        if ids <= rows.keys() or time.monotonic() > deadline:
            return rows
        time.sleep(2)


@pytest.mark.real
def test_stats_hypervisors_reports_degraded_and_reason(admin_client):
    conn = _connect()
    sfx = uuid.uuid4().hex[:8]
    with_reason = f"e2e_real_degraded_{sfx}"
    without_reason = f"e2e_real_degraded_noreason_{sfx}"
    healthy = f"e2e_real_healthy_{sfx}"
    reason = "storage: not responding: /isard/groups"
    try:
        r.table("hypervisors").insert(
            [
                _hypervisor(with_reason, {"is_degraded": True, "reason": reason}),
                _hypervisor(without_reason, {"is_degraded": True, "reason": None}),
                _hypervisor(healthy, {"is_degraded": False, "reason": None}),
            ],
            conflict="replace",
        ).run(conn)

        rows = _rows_for(admin_client, {with_reason, without_reason, healthy})

        assert rows.get(with_reason) == {
            "id": with_reason,
            "status": "Offline",
            "only_forced": True,
            "degraded": True,
            "degraded_reason": reason,
        }, rows.get(with_reason)
        assert (
            rows.get(without_reason, {}).get("degraded_reason") == "unknown"
        ), rows.get(without_reason)
        assert rows.get(healthy) == {
            "id": healthy,
            "status": "Offline",
            "only_forced": True,
        }, rows.get(healthy)
    finally:
        r.table("hypervisors").get_all(
            with_reason, without_reason, healthy
        ).delete().run(conn)
        conn.close()
