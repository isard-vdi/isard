# SPDX-License-Identifier: AGPL-3.0-or-later
"""The local egress gateway has to be an ANYCAST address, and stay one.

Every hypervisor puts the same address at the end of the guests network, and
every hypervisor shares one VLAN-4095 broadcast domain over geneve. That only
works if the address never crosses the tunnel — otherwise two hypervisors
answer for it, the bridges learn each other's MAC and desktops start leaving
through a neighbour's uplink.

The three containment flows from ``setup.sh`` are what makes it local by
construction. These tests are the reason to trust that claim.
"""
from __future__ import annotations

GUEST = "52:54:00:00:40:01"
GW = "10.2.255.254"
GW_MAC = "52:54:00:00:40:fe"
REMOTE_GW_FRAME = f"in_port=1,dl_src={GW_MAC},dl_dst=ff:ff:ff:ff:ff:ff"


def _hypervisor(switch, contained=True):
    """A hypervisor bridge: 1 is the geneve tunnel, 2 the desktop, 3 inet-gw."""
    switch.add_bridge("ovsbr0", rstp=True)
    switch.add_port("ovsbr0", "tunnel0", ofport=1)
    switch.add_port("ovsbr0", "vnet0", ofport=2, tag=4095)
    switch.add_port("ovsbr0", "inet-gw", ofport=3, tag=4095)
    switch.wait_forwarding("ovsbr0", ("tunnel0", "vnet0", "inet-gw"))
    # What main already installs: the tunnel delivers into the VLAN by NORMAL.
    switch.add_flow("ovsbr0", "priority=211,in_port=1,dl_vlan=4095,actions=NORMAL")
    # An access port's frames are UNTAGGED in the OpenFlow match — the tag is
    # only pushed on output to a trunk — so a containment rule aimed at both
    # the local desktops and the tunnel cannot carry dl_vlan.
    if contained:
        switch.add_flow(
            "ovsbr0",
            f"priority=213,arp,arp_op=1,arp_tpa={GW}," "actions=strip_vlan,output:3",
        )
        switch.add_flow(
            "ovsbr0", f"priority=214,arp,in_port=1,arp_spa={GW},actions=drop"
        )
        switch.add_flow("ovsbr0", f"priority=214,ip,in_port=1,nw_src={GW},actions=drop")
    return switch


def _arp_for_gateway(switch):
    return switch.ports_reached(
        "ovsbr0",
        f"in_port=2,dl_src={GUEST},dl_dst=ff:ff:ff:ff:ff:ff,dl_type=0x0806,"
        f"arp_op=1,arp_spa=10.2.1.5,arp_tpa={GW}",
    )


def test_the_desktop_resolves_the_gateway_on_its_own_hypervisor(switch):
    assert _arp_for_gateway(_hypervisor(switch)) == {"inet-gw"}


def test_the_gateway_arp_never_reaches_the_tunnel(switch):
    """The load-bearing assertion: if this leaks, two hypervisors answer for
    the same address and desktops leave through a neighbour's uplink."""
    assert "tunnel0" not in _arp_for_gateway(_hypervisor(switch))


def test_without_the_containment_flow_the_arp_does_leak(switch):
    """The control. Without it the two tests above prove nothing about the
    flows — they would pass on any bridge that simply drops everything."""
    assert "tunnel0" in _arp_for_gateway(_hypervisor(switch, contained=False))


def test_a_remote_gateway_announcement_is_dropped(switch):
    reached = _hypervisor(switch).ports_reached(
        "ovsbr0",
        f"{REMOTE_GW_FRAME},dl_vlan=4095,dl_type=0x0806,arp_op=2,"
        f"arp_spa={GW},arp_tpa=10.2.1.5",
    )
    assert reached == set()


def test_remote_traffic_sourced_from_the_gateway_is_dropped(switch):
    reached = _hypervisor(switch).ports_reached(
        "ovsbr0",
        f"in_port=1,dl_src={GW_MAC},dl_dst={GUEST},dl_vlan=4095,dl_type=0x0800,"
        f"nw_src={GW},nw_dst=10.2.1.5,nw_proto=6",
    )
    assert reached == set()


def test_ordinary_tunnel_traffic_still_gets_through(switch):
    """Containment must cut the gateway address and nothing else.

    The frame carries dl_vlan=4095 because that is what the tunnel really
    puts on the wire: without it, OVS 4.0 delivers to no port at all while
    3.7 floods, which is the version difference this umbrella exists for.
    """
    reached = _hypervisor(switch).ports_reached(
        "ovsbr0",
        f"in_port=1,dl_src=52:54:00:99:99:99,dl_dst={GUEST},dl_vlan=4095,"
        f"dl_type=0x0800,nw_src=10.2.9.9,nw_dst=10.2.1.5,nw_proto=6",
    )
    assert reached
