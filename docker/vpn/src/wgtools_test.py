#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the wireguard key rotation handling in ``Wg``.

Deps (``iptc``/``simple_iptools``/``rethinkdb``/``changefeed_models``) only
exist in the isard-vpn image: ``PYTHONPATH=/src pytest``.
"""

import contextlib
from unittest.mock import MagicMock

import wgtools


class _StubKeys:
    update_clients = False

    def new_client_keys(self):
        return {"private": "PRIV", "public": "PUB"}


def _bare_wg():
    wg = wgtools.Wg.__new__(wgtools.Wg)
    wg.table = "users"
    wg.interface = "wg0"
    wg.allowed_client_nets = "0.0.0.0/0"
    wg.clients_reserved_ips = []
    wg.keys = _StubKeys()
    return wg


def test_up_peer_skips_not_ready_keys():
    wg = _bare_wg()
    peer = {
        "id": "u1",
        "active": True,
        "vpn": {"wireguard": {"Address": "10.0.0.5", "keys": False}},
    }
    assert wg.up_peer(peer) is False


def test_init_peers_regenerates_reset_keys(monkeypatch):
    wg = _bare_wg()
    up_called, gen_called = [], []
    monkeypatch.setattr(wg, "up_peer", lambda p: up_called.append(p))
    monkeypatch.setattr(wg, "_to_model", lambda p: p)
    monkeypatch.setattr(
        wg,
        "gen_new_peer",
        lambda p: gen_called.append(p)
        or {
            "id": p["id"],
            "active": True,
            "vpn": {"wireguard": {"keys": {"public": "NEW"}}},
        },
    )

    @contextlib.contextmanager
    def _fake_conn():
        yield MagicMock()

    monkeypatch.setattr(wgtools, "vpn_rethink_conn", _fake_conn)

    healthy = {
        "id": "ok",
        "active": True,
        "vpn": {
            "wireguard": {
                "Address": "10.0.0.2",
                "keys": {"public": "P"},
                "extra_client_nets": None,
            }
        },
    }
    reset = {
        "id": "reset",
        "active": True,
        "vpn": {
            "wireguard": {
                "Address": "10.0.0.3",
                "keys": False,
                "extra_client_nets": None,
            }
        },
    }
    nowg = {"id": "nowg", "active": True, "vpn": {"wireguard": False}}

    def fake_table(name):
        t = MagicMock()
        t.pluck.return_value.run.return_value = (
            [] if name == "remotevpn" else [healthy, reset, nowg]
        )
        return t

    monkeypatch.setattr(wgtools, "r", MagicMock(table=fake_table))
    wg.init_peers()

    assert reset["vpn"]["wireguard"]["keys"] == {"private": "PRIV", "public": "PUB"}
    assert any(p["id"] == "nowg" for p in gen_called)
    for p in up_called:
        wg_cfg = p.get("vpn", {}).get("wireguard")
        assert isinstance(wg_cfg, dict) and wg_cfg.get("keys")
