# SPDX-License-Identifier: AGPL-3.0-or-later
"""The bandwidth ceilings, checked on a real datapath.

The acceptance gate for this phase is "assign a profile to a group and see
its rate in a desktop's meters", so what has to be proven here is that the
meter OVS actually installs carries the rate the engine resolved, in kbps,
and that the desktop's flows reference it.

``ovs-ofctl`` needs OpenFlow 1.3 for meters and the harness's ``add_flow``
does not ask for it, so these go through a local helper. It belongs in
``DummySwitch`` once the harness MR is merged and can take new scope.
"""
from __future__ import annotations

import re

GUEST = "52:54:00:00:30:05"
METER_UP = 526  # meter_base(100 + 42*10) + 6, mirroring ovs_worker
METER_DOWN = 527


def _ofctl13(switch, *args):
    return switch._appctl_tool(["ovs-ofctl", "-O", "OpenFlow13", *args])


def _bridge_with_meters(switch, up_kbps=0, down_kbps=0):
    switch.add_bridge("ovsbr0", rstp=True)
    switch.add_port("ovsbr0", "tunnel0", ofport=1)
    switch.add_port("ovsbr0", "vnet0", ofport=42, tag=4095)
    switch.wait_forwarding("ovsbr0", ("tunnel0", "vnet0"))

    up_action, down_action = "", ""
    if up_kbps:
        _ofctl13(
            switch,
            "add-meter",
            "ovsbr0",
            f"meter={METER_UP},kbps,burst,bands=type=drop,"
            f"rate={up_kbps},burst_size={max(up_kbps // 2, 1000)}",
        )
        up_action = f"meter:{METER_UP},"
    if down_kbps:
        _ofctl13(
            switch,
            "add-meter",
            "ovsbr0",
            f"meter={METER_DOWN},kbps,burst,bands=type=drop,"
            f"rate={down_kbps},burst_size={max(down_kbps // 2, 1000)}",
        )
        down_action = f"meter:{METER_DOWN},"

    _ofctl13(
        switch,
        "add-flow",
        "ovsbr0",
        f"priority=204,ip,in_port=42,dl_src={GUEST},actions={up_action}NORMAL",
    )
    _ofctl13(
        switch,
        "add-flow",
        "ovsbr0",
        f"priority=221,in_port=1,dl_dst={GUEST},dl_vlan=4095,"
        f"actions={down_action}strip_vlan,output:42",
    )
    return switch


def _meter_config(switch):
    return _ofctl13(switch, "dump-meters", "ovsbr0")


def test_the_switch_accepts_kbps_meters_at_all(switch):
    """The premise of the whole design: OVS meters can rate-limit by
    bandwidth, not only by packet rate."""
    features = _ofctl13(_bridge_with_meters(switch), "meter-features", "ovsbr0")
    assert "kbps" in features


def test_an_upload_ceiling_is_installed_with_its_rate(switch):
    config = _meter_config(_bridge_with_meters(switch, up_kbps=1000))
    assert re.search(rf"meter={METER_UP} kbps burst", config)
    assert "rate=1000" in config


def test_both_directions_get_their_own_meter(switch):
    config = _meter_config(_bridge_with_meters(switch, up_kbps=1000, down_kbps=10000))
    assert f"meter={METER_UP}" in config and f"meter={METER_DOWN}" in config
    assert "rate=1000" in config and "rate=10000" in config


def test_the_desktop_flows_reference_the_meters(switch):
    """A meter nothing points at limits nothing — this is the half that a
    config dump alone would not catch."""
    flows = _ofctl13(
        _bridge_with_meters(switch, up_kbps=1000, down_kbps=10000),
        "dump-flows",
        "ovsbr0",
    )
    assert f"meter:{METER_UP}" in flows
    assert f"meter:{METER_DOWN}" in flows


def test_the_meter_counts_the_desktop_traffic(switch):
    """The acceptance gate: the rate shows up in the desktop's meters. The
    flow_count is what binds a meter to a desktop's rule."""
    switch = _bridge_with_meters(switch, up_kbps=1000)
    stats = _ofctl13(switch, "meter-stats", "ovsbr0")
    assert re.search(rf"meter:{METER_UP} flow_count:1", stats)


def test_without_a_profile_no_meter_exists(switch):
    """Every install until somebody assigns a profile."""
    config = _meter_config(_bridge_with_meters(switch))
    assert f"meter={METER_UP}" not in config
    assert f"meter={METER_DOWN}" not in config
