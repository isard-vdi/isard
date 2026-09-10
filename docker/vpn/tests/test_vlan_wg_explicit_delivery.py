# SPDX-License-Identifier: AGPL-3.0-or-later
"""The VPN must reach the internal ``vlan-wg`` port for the two things a guest
needs from it without relying on the ``NORMAL`` flood, because OVS 4.0 drops
that non-RSTP-participating internal port out of the flood once RSTP is on.

Only the guest per-peer flows change; the bridge-wide flood is left untouched
(no ``no-flood``), so 3.7.1's delivery to bastion/samba/local is unchanged:

  * DHCP (``priority=451,udp,tp_src=68,tp_dst=67``): ``strip_vlan,output:vlan-wg``
    — explicit to dnsmasq, never a bare ``NORMAL`` (so no duplicate DISCOVER and
    no doubled OFFER on 3.7.1, where NORMAL would also reach vlan-wg).
  * gateway ARP (new ``priority=452,arp,arp_op=1,arp_tpa=<gateway>``):
    ``strip_vlan,output:vlan-wg`` — the one ARP 4.0 drops to the internal port,
    scoped to the gateway so it never shadows other ARP.
  * all other ARP (``priority=451,arp``): stays ``NORMAL`` — samba/bastion/peer
    flood and learned unicast replies are unaffected (those are RSTP trunks).

Mutation that must turn these red: putting either explicit flow back on
``actions=NORMAL``, or dropping/​broadening the priority=452 gateway flow.
"""

from __future__ import annotations

from unittest.mock import patch

from isardvdi_vpn import wgadmin


def _flows(mock_run):
    joined = [" ".join(c.args[0]) for c in mock_run.call_args_list]
    return [c for c in joined if "add-flow" in c]


def _one(flows, needle):
    hits = [f for f in flows if needle in f]
    assert (
        len(hits) == 1
    ), f"expected one flow matching {needle!r}, got {len(hits)}: {hits}"
    return hits[0]


def _assert_explicit_delivery(mock_run):
    flows = _flows(mock_run)

    # DHCP: explicit to dnsmasq on vlan-wg, never a bare NORMAL flood.
    dhcp = _one(flows, "priority=451,udp")
    assert "tp_src=68,tp_dst=67" in dhcp
    assert "actions=strip_vlan,output:vlan-wg" in dhcp
    assert "NORMAL" not in dhcp

    # Gateway ARP: the one ARP 4.0 drops to the internal port; explicit to
    # vlan-wg, scoped to the gateway, never NORMAL.
    gw_arp = _one(flows, "priority=452,arp")
    assert "arp_op=1" in gw_arp and "arp_tpa=10.2.0.1" in gw_arp
    assert "actions=strip_vlan,output:vlan-wg" in gw_arp
    assert "NORMAL" not in gw_arp

    # Every other ARP stays on NORMAL (samba/bastion/peer flood, learned
    # replies): the bridge-wide flood is not touched by this fix.
    arp_norm = _one(flows, "priority=451,arp")
    assert arp_norm.endswith("actions=NORMAL")
    assert "output:vlan-wg" not in arp_norm


def test_plain_geneve_delivers_dhcp_and_gateway_arp_explicitly(
    wgtools_hyper, wgtools_module
):
    """wgtools.Wg.up_peer, plain-geneve (BFD) branch."""
    peer = {"id": "hyper-new", "hostname": "hyper-new.lan", "vpn": None}
    with (
        patch.object(wgtools_module, "check_output", side_effect=["", "42"]),
        patch.object(wgtools_module.subprocess, "run") as mock_run,
        patch.object(wgtools_module.socket, "gethostbyname", return_value="192.0.2.1"),
    ):
        assert wgtools_hyper.up_peer(peer) is True
    _assert_explicit_delivery(mock_run)


def test_wg_geneve_delivers_dhcp_and_gateway_arp_explicitly(
    wgtools_hyper, wgtools_module
):
    """wgtools.Wg.up_peer, WireGuard+geneve (no-BFD) branch."""
    peer = {
        "id": "hyper-new",
        "hostname": "hyper-new.internal",
        "vpn": {
            "wireguard": {
                "Address": "192.0.2.42",
                "keys": {"public": "pk"},
                "extra_client_nets": None,
                "AllowedIPs": "0.0.0.0/0",
            }
        },
    }
    with (
        patch.object(wgtools_module, "check_output", side_effect=["", "42"]),
        patch.object(wgtools_module.subprocess, "run") as mock_run,
    ):
        assert wgtools_hyper.up_peer(peer) is True
    _assert_explicit_delivery(mock_run)


def test_wgadmin_geneve_port_delivers_dhcp_and_gateway_arp_explicitly(monkeypatch):
    """wgadmin.ensure_geneve_port."""
    monkeypatch.setenv("WG_HYPERS_PORT", "4443")
    monkeypatch.setattr(
        wgadmin.socket, "gethostbyname", lambda h: "192.0.2.9", raising=False
    )
    with (
        patch.object(wgadmin, "check_output", side_effect=["", "42"]),
        patch.object(wgadmin, "subprocess") as sp,
    ):
        assert wgadmin.ensure_geneve_port("isard-hypervisor", "hyper.local") is True
    _assert_explicit_delivery(sp.run)
