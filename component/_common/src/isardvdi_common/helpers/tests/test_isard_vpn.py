#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``IsardVpn`` vpn config rendering.

Every level of ``vpn.wireguard.keys.private`` can be False in the db (a peer
without vpn, a rotation blanking keys, a geneve-only hypervisor with no peer
subtree). None of those shapes may reach the f-string in get_wireguard_file:
they'd raise ``TypeError: 'bool' object is not subscriptable`` and surface as a
500. Each must map to a typed 4xx, and permanent states (404/409) must be
distinguishable from the transient init race (428) so clients stop retrying.
"""

from unittest.mock import MagicMock

import pytest
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.isard_vpn import IsardVpn

WG_OK = {
    "Address": "10.1.0.5/32",
    "AllowedIPs": "10.0.0.0/8",
    "keys": {"private": "privkey", "public": "pubkey"},
}
SERVER_KEYS = {"private": "srv-priv", "public": "srv-pub"}


@pytest.fixture
def stub_rdb(monkeypatch):
    """Stub the rethink layer: r.table(...) yields the peer, r.db(...) the config."""
    from isardvdi_common.helpers import isard_vpn as mod

    class _Ctx:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(mod.IsardVpn, "_rdb_context", classmethod(lambda cls: _Ctx()))
    monkeypatch.setattr(
        type(mod.IsardVpn),
        "_rdb_connection",
        property(lambda self: MagicMock(name="conn")),
    )

    state = {"peer": None, "sysconfig": {}}

    def _table(name):
        table = MagicMock(name=f"r.table({name})")
        table.get.return_value.pluck.return_value.run.return_value = state["peer"]
        return table

    def _db(name):
        db = MagicMock(name=f"r.db({name})")
        db.table.return_value.get.return_value.run.return_value = state["sysconfig"]
        return db

    monkeypatch.setattr(mod.r, "table", _table)
    monkeypatch.setattr(mod.r, "db", _db)
    monkeypatch.delenv("GENEVE_ONLY_INFRA", raising=False)
    yield state


def _set_peer(state, vpn, kind="users"):
    state["peer"] = {"id": "u1", "vpn": vpn}
    keys_field = "vpn_hypers" if kind == "hypers" else "vpn_users"
    state["sysconfig"] = {keys_field: {"wireguard": {"keys": SERVER_KEYS}}}


class TestVpnDataPeerShapes:
    def test_user_without_vpn_is_not_found_not_a_retry(self, stub_rdb):
        _set_peer(stub_rdb, False)

        with pytest.raises(Error) as exc:
            IsardVpn.vpn_data("users", "config", False, "u1")

        assert exc.value.status_code == 404
        assert exc.value.error["description_code"] == "vpn_not_configured"

    def test_blanked_keys_are_a_typed_retry_not_a_type_error(self, stub_rdb):
        _set_peer(stub_rdb, {"wireguard": {**WG_OK, "keys": False}})

        with pytest.raises(Error) as exc:
            IsardVpn.vpn_data("users", "config", False, "u1")

        assert exc.value.status_code == 428
        assert exc.value.error["description_code"] == "vpn_peer_not_ready"

    def test_missing_wireguard_subtree_is_the_init_race(self, stub_rdb):
        _set_peer(stub_rdb, {"tunneling_mode": "wireguard+geneve"})

        with pytest.raises(Error) as exc:
            IsardVpn.vpn_data("users", "config", False, "u1")

        assert exc.value.status_code == 428
        assert exc.value.error["description_code"] == "vpn_peer_not_ready"

    def test_valid_peer_renders_the_config(self, stub_rdb):
        _set_peer(stub_rdb, {"wireguard": WG_OK})

        result = IsardVpn.vpn_data("users", "config", False, "u1")

        assert result["ext"] == "conf"
        assert "PrivateKey = privkey" in result["content"]
        assert "AllowedIPs = 10.0.0.0/8" in result["content"]

    def test_geneve_only_hypervisor_without_peer_subtree_is_a_conflict(
        self, stub_rdb, monkeypatch
    ):
        monkeypatch.setenv("GENEVE_ONLY_INFRA", "true")
        _set_peer(stub_rdb, {"tunneling_mode": "geneve"}, kind="hypers")

        with pytest.raises(Error) as exc:
            IsardVpn.vpn_data("hypers", "config", "", "h1")

        assert exc.value.status_code == 409
        assert exc.value.error["description_code"] == "vpn_wireguard_disabled"


class TestGetWireguardFile:
    """The one funnel every caller goes through, guards upstream or not."""

    @pytest.mark.parametrize(
        "peer",
        [
            {"id": "p1", "vpn": False},
            {"id": "p1", "vpn": {"wireguard": False}},
            {"id": "p1", "vpn": {"wireguard": {**WG_OK, "keys": False}}},
            {"id": "p1", "vpn": {}},
        ],
        ids=["no-vpn", "no-wireguard", "blanked-keys", "empty-vpn"],
    )
    def test_unrenderable_peer_raises_typed_error(self, peer):
        with pytest.raises(Error) as exc:
            IsardVpn.get_wireguard_file(
                "vpn.example.org", peer, "443", "1420", None, SERVER_KEYS
            )

        assert exc.value.status_code == 428
        assert exc.value.error["description_code"] == "vpn_peer_not_ready"
