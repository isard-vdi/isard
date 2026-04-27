# SPDX-License-Identifier: AGPL-3.0-or-later

"""Pydantic schema tests for ``api/schemas/vpn.py``."""

import pytest
from api.schemas.vpn import (
    VpnConnectionRequest,
    VpnDisconnectListItem,
    VpnDisconnectListRequest,
)
from pydantic import ValidationError


class TestVpnConnectionRequest:
    @pytest.mark.parametrize("missing", ["remote_ip", "remote_port"])
    def test_required(self, missing):
        payload = {"remote_ip": "1.2.3.4", "remote_port": 51820}
        del payload[missing]
        with pytest.raises(ValidationError):
            VpnConnectionRequest(**payload)

    def test_port_string_coerced(self):
        """remote_port: int — Pydantic coerces "51820" → 51820. Pin so
        a strict-mode flip is noticed."""
        r = VpnConnectionRequest(remote_ip="1.2.3.4", remote_port="51820")
        assert r.remote_port == 51820


class TestVpnDisconnectListItem:
    @pytest.mark.parametrize("missing", ["kind", "client_ip"])
    def test_required(self, missing):
        payload = {"kind": "wireguard", "client_ip": "10.0.0.1"}
        del payload[missing]
        with pytest.raises(ValidationError):
            VpnDisconnectListItem(**payload)


class TestVpnDisconnectListRequest:
    """RootModel wrapping a List[VpnDisconnectListItem] — the request
    body IS the list, no wrapper key. Pin the unwrap behavior so a
    future change to a typed wrapper is intentional."""

    def test_accepts_list(self):
        r = VpnDisconnectListRequest(
            [
                {"kind": "wireguard", "client_ip": "10.0.0.1"},
                {"kind": "wireguard", "client_ip": "10.0.0.2"},
            ]
        )
        assert len(r.root) == 2
        assert r.root[0].client_ip == "10.0.0.1"

    def test_accepts_empty_list(self):
        r = VpnDisconnectListRequest([])
        assert r.root == []

    def test_invalid_item_propagates(self):
        with pytest.raises(ValidationError):
            VpnDisconnectListRequest([{"kind": "wireguard"}])  # client_ip missing
