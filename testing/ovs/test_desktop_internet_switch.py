# SPDX-License-Identifier: AGPL-3.0-or-later
"""The internet switch, checked on a real datapath rather than on the flow text.

``ovs_worker._flow_add`` emits two rules for a desktop whose ``internet`` is
off: an allow restricted to the guests network at priority 204 and a drop at
203. Unit tests pin that it emits them; only ``ofproto/trace`` says whether a
frame to the outside actually stops, and — the half that matters more — that
everything internal still gets through.

The port numbering mirrors a hypervisor bridge: 1 is the geneve tunnel to the
VPN (and so the way out), 2 is the desktop's vnet.
"""
from __future__ import annotations

GUEST = "52:54:00:00:20:05"
GUESTS_NET = "10.2.0.0/16"
INSIDE = "10.2.1.7"  # another desktop
GATEWAY = "10.2.0.1"  # the VPN gateway's DNS
OUTSIDE = "8.8.8.8"


def _restricted_desktop(switch):
    """A VLAN-4095 desktop port with the internet switch off."""
    switch.add_bridge("ovsbr0", rstp=True)
    switch.add_port("ovsbr0", "tunnel0", ofport=1)
    switch.add_port("ovsbr0", "vnet0", ofport=2, tag=4095)
    switch.wait_forwarding("ovsbr0", ("tunnel0", "vnet0"))
    switch.add_flow(
        "ovsbr0",
        f"priority=204,ip,in_port=2,dl_src={GUEST},nw_dst={GUESTS_NET},actions=NORMAL",
    )
    switch.add_flow("ovsbr0", f"priority=203,ip,in_port=2,dl_src={GUEST},actions=drop")
    return switch


def _allowed_desktop(switch):
    """The same port with the switch on — what main emits today."""
    switch.add_bridge("ovsbr0", rstp=True)
    switch.add_port("ovsbr0", "tunnel0", ofport=1)
    switch.add_port("ovsbr0", "vnet0", ofport=2, tag=4095)
    switch.wait_forwarding("ovsbr0", ("tunnel0", "vnet0"))
    switch.add_flow(
        "ovsbr0", f"priority=204,ip,in_port=2,dl_src={GUEST},actions=NORMAL"
    )
    return switch


def _egress(switch, nw_dst):
    return switch.ports_reached(
        "ovsbr0",
        f"in_port=2,dl_src={GUEST},dl_dst=52:54:00:00:00:01,"
        f"dl_type=0x0800,nw_src=10.2.1.5,nw_dst={nw_dst},nw_proto=6",
    )


def test_a_restricted_desktop_does_not_reach_the_outside(switch):
    assert _egress(_restricted_desktop(switch), OUTSIDE) == set()


def test_a_restricted_desktop_still_reaches_another_desktop(switch):
    assert _egress(_restricted_desktop(switch), INSIDE)


def test_a_restricted_desktop_still_reaches_the_gateway(switch):
    """DNS and the infrastructure services live on the gateway; cutting
    internet must not cut those."""
    assert _egress(_restricted_desktop(switch), GATEWAY)


def test_an_allowed_desktop_reaches_the_outside(switch):
    """The control: without the drop, the same frame leaves through the
    tunnel. If this ever fails, the two tests above prove nothing."""
    assert _egress(_allowed_desktop(switch), OUTSIDE)
