#
#   Copyright © 2026 Josep Maria Viñolas Auquer
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI.  If not, see <http://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later
"""The lease hook must pin the guest's source address *and* stop its traffic to
the gateway depending on the bridge still remembering the gateway's MAC.

From OVS 4.0 the internal ``vlan-wg`` port is out of the ``NORMAL`` flood, so
once that MAC ages out (300s by default) every frame the guest sends towards the
gateway -- to it and through it -- is flooded to bastion and samba and lost.
Delivering it explicitly from table 2 keeps the source-address check in front of
it, which delivering it from table 0 would have skipped.

Mutation that must turn these red: dropping the priority=110 flow, moving it out
of table 2, or widening it so it no longer carries both ``dl_src`` and
``nw_src``.
"""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

HOOK = Path(__file__).resolve().parents[1] / "dnsmasq-hook" / "update-client-ips.sh"
MAC = "52:54:00:00:00:50"
IP = "192.0.2.50"
GATEWAY_MAC = "02:00:00:00:00:01"


def _stub(directory, name, body):
    path = directory / name
    path.write_text(f"#!/bin/sh\n{body}\n")
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _run_hook(tmp_path, action=("add", MAC, IP, "desktop"), gateway_mac=GATEWAY_MAC):
    binaries = tmp_path / "bin"
    binaries.mkdir()
    recorded = tmp_path / "ovs-ofctl.log"
    _stub(binaries, "ovs-ofctl", f'printf "%s\\n" "$*" >> {recorded}')
    _stub(binaries, "arp", "exit 0")
    link = f"1: vlan-wg: <BROADCAST> mtu 1386 link/ether {gateway_mac} brd ff:ff:ff:ff:ff:ff"
    _stub(binaries, "ip", f'printf "%s\\n" "{link}"' if gateway_mac else "exit 1")
    subprocess.run(
        ["sh", str(HOOK), *action],
        check=True,
        capture_output=True,
        env={**os.environ, "PATH": f"{binaries}:{os.environ['PATH']}"},
    )
    return recorded.read_text().splitlines() if recorded.exists() else []


def _one(flows, needle):
    hits = [f for f in flows if needle in f]
    assert len(hits) == 1, f"expected one flow matching {needle!r}, got {hits}"
    return hits[0]


@pytest.mark.parametrize("action", ["add", "old"])
def test_the_guest_gets_both_flows_on_lease_and_on_renewal(tmp_path, action):
    flows = _run_hook(tmp_path, action=(action, MAC, IP, "desktop"))
    _one(flows, "priority=100")
    _one(flows, "priority=110")


def test_traffic_to_the_gateway_mac_is_delivered_without_relying_on_learning(tmp_path):
    flow = _one(_run_hook(tmp_path), "priority=110")
    assert "table=2" in flow
    assert f"dl_dst={GATEWAY_MAC}" in flow
    assert "actions=strip_vlan,output:vlan-wg" in flow
    assert "NORMAL" not in flow


def test_the_explicit_delivery_still_carries_the_source_address_check(tmp_path):
    flow = _one(_run_hook(tmp_path), "priority=110")
    assert f"dl_src={MAC}" in flow, "a guest could send as any address"
    assert f"nw_src={IP}" in flow, "a guest could spoof its address to the gateway"


def test_the_explicit_delivery_outranks_the_plain_pinning_flow(tmp_path):
    flows = _run_hook(tmp_path)
    assert int(_one(flows, "priority=110").split("priority=")[1][:3]) > int(
        _one(flows, "priority=100").split("priority=")[1][:3]
    )


def test_nothing_is_programmed_when_the_gateway_mac_cannot_be_read(tmp_path):
    flows = _run_hook(tmp_path, gateway_mac="")
    _one(flows, "priority=100")
    assert not [f for f in flows if "priority=110" in f]


def test_a_released_lease_programs_no_flow_at_all(tmp_path):
    assert not _run_hook(tmp_path, action=("del", MAC, IP, "desktop"))
