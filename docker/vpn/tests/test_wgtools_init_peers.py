# SPDX-License-Identifier: AGPL-3.0-or-later
"""init_peers fast-startup path: O(1) set-based IP allocation, batched
db-backfill, and background up_peer draining.

Locks in the perf rework: reserved IPs are a set (membership is O(1), not a
linear scan over every user), inserts are chunked instead of one terminal
insert, and up_peer runs off the main thread so init_peers returns before the
wgadmin loop starts serving changefeed events.
"""
from __future__ import annotations

import ipaddress
import threading
import time
from unittest.mock import MagicMock


def _users_wg(wgtools_module, reserved=None):
    Wg = wgtools_module.Wg
    wg = Wg.__new__(Wg)
    wg.table = "users"
    wg.interface = "users"
    wg.server_net = ipaddress.ip_network("10.1.0.0/24")
    wg.server_ip = "10.1.0.1"
    wg.clients_reserved_ips = {wg.server_ip} if reserved is None else set(reserved)
    wg.allowed_client_nets = "10.2.0.0/24"
    wg.uipt = MagicMock()
    wg.keys = MagicMock()
    wg.keys.update_clients = False
    wg.keys.new_client_keys.return_value = {"public": "pub", "private": "priv"}
    return wg


class _FakeReQL:
    def __init__(self, recorder, table, reads):
        self._rec, self._table, self._reads = recorder, table, reads
        self._insert = None

    def pluck(self, *a, **k):
        return self

    def filter(self, *a, **k):
        return self

    def insert(self, batch, conflict=None):
        self._insert = list(batch)
        return self

    def run(self, conn):
        if self._insert is not None:
            self._rec.append((self._table, self._insert))
            return {"inserted": len(self._insert)}
        return list(self._reads.get(self._table, []))


class _FakeR:
    def __init__(self, recorder, reads):
        self._rec, self._reads = recorder, reads

    def table(self, name, *a, **k):
        return _FakeReQL(self._rec, name, self._reads)


class _FakeConnCM:
    def __enter__(self):
        return object()

    def __exit__(self, *a):
        return False


def _join_up_threads():
    for t in threading.enumerate():
        if t.name.startswith("init_peers_up_"):
            t.join(timeout=5)


# ---- (B) O(1) set-based IP allocation ------------------------------------


def test_gen_client_ip_set_and_deterministic(wgtools_module):
    wg = _users_wg(wgtools_module)
    assert isinstance(wg.clients_reserved_ips, set)
    assert wg.gen_client_ip() == "10.1.0.2"
    assert wg.gen_client_ip() == "10.1.0.3"
    assert {"10.1.0.2", "10.1.0.3"} <= wg.clients_reserved_ips


def test_gen_client_ip_skips_reserved(wgtools_module):
    wg = _users_wg(wgtools_module, reserved={"10.1.0.1", "10.1.0.2"})
    assert wg.gen_client_ip() == "10.1.0.3"


# ---- (C) batched backfill flush -----------------------------------------


def test_flush_peers_batch_inserts_and_noop_on_empty(wgtools_module, monkeypatch):
    rec = []
    monkeypatch.setattr(wgtools_module, "r", _FakeR(rec, {}))
    monkeypatch.setattr(wgtools_module, "vpn_rethink_conn", _FakeConnCM)
    wg = _users_wg(wgtools_module)
    wg._flush_peers_batch("users", [{"id": "a"}, {"id": "b"}], 2, 2, time.monotonic())
    wg._flush_peers_batch("users", [], 2, 2, time.monotonic())  # no-op
    assert rec == [("users", [{"id": "a"}, {"id": "b"}])]


# ---- (D) background up_peer draining -------------------------------------


def test_background_up_peers_drains_all_and_isolates_errors(wgtools_module):
    wg = _users_wg(wgtools_module)
    seen = []

    def fake_up(peer):
        pid = peer["id"] if isinstance(peer, dict) else peer
        if pid == "boom":
            raise RuntimeError("bad peer")
        seen.append(pid)
        return True

    wg.up_peer = fake_up
    wg._to_model = lambda d: d
    wg._start_background_up_peers(
        [{"id": "u1"}, {"id": "boom"}, {"id": "u2"}], [{"id": "rv1"}]
    )
    _join_up_threads()
    # boom raised but did not abort the rest, incl. the remotevpn peer.
    assert seen == ["u1", "u2", "rv1"]


def test_start_background_up_peers_noop_when_empty(wgtools_module):
    wg = _users_wg(wgtools_module)
    before = threading.active_count()
    wg._start_background_up_peers([], [])
    assert threading.active_count() == before


# ---- (C+D) init_peers orchestration integration --------------------------


def test_init_peers_batches_inserts_and_backgrounds_up_peer(
    wgtools_module, monkeypatch
):
    rec = []
    reads = {
        "users": [
            {"id": "u1", "active": True},  # lazy-init (no vpn)
            {"id": "u2", "active": False},  # lazy-init, inactive
            {
                "id": "u3",
                "active": True,  # existing valid, keys ok
                "vpn": {"wireguard": {"Address": "10.1.0.5", "keys": {"public": "k"}}},
            },
            {
                "id": "u4",
                "active": True,  # rotation requested: keys falsy
                "vpn": {"wireguard": {"Address": "10.1.0.6", "keys": False}},
            },
            {"id": "u5", "active": True, "vpn": None},  # null vpn subtree (regression)
        ],
        "remotevpn": [{"id": "rv1"}],  # lazy-init
    }
    monkeypatch.setattr(wgtools_module, "r", _FakeR(rec, reads))
    monkeypatch.setattr(wgtools_module, "vpn_rethink_conn", _FakeConnCM)

    wg = _users_wg(wgtools_module)
    wg._INIT_PEERS_BATCH = 2  # force chunking
    up_seen = []
    wg.up_peer = lambda peer: up_seen.append(
        peer["id"] if isinstance(peer, dict) else peer
    )
    wg._to_model = lambda d: d
    # gen_new_peer returns an id+vpn dict WITHOUT 'active' (matches real impl).
    wg.gen_new_peer = lambda peer, extra_client_nets=None: {
        "id": peer["id"],
        "vpn": {"wireguard": {"Address": wg.gen_client_ip(), "keys": {"public": "k"}}},
    }

    wg.init_peers(reset=False)
    _join_up_threads()

    assert isinstance(wg.clients_reserved_ips, set)

    users_inserts = [batch for tbl, batch in rec if tbl == "users"]
    rv_inserts = [batch for tbl, batch in rec if tbl == "remotevpn"]
    # chunked (batch=2 over 4 creates), not one terminal insert
    assert len(users_inserts) >= 2
    created_ids = {p["id"] for batch in users_inserts for p in batch}
    # u5 (vpn=None) is treated as lazy-init instead of crashing init_peers.
    assert created_ids == {"u1", "u2", "u4", "u5"}
    assert {p["id"] for batch in rv_inserts for p in batch} == {"rv1"}

    # Background up_peer covers active targets only: u3, u4 and rv1. u1/u2 were
    # created without 'active', so the original gating is preserved.
    assert sorted(up_seen) == ["rv1", "u3", "u4"]
