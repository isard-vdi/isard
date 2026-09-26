# SPDX-License-Identifier: AGPL-3.0-or-later
"""Running desktops must keep their table 2 pin while dnsmasq walks its leases."""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
from isardvdi_vpn import lease_pins

NOW = 1_800_000_000
GATEWAY = "aa:bb:cc:00:00:01"
LINK = f"7: vlan-wg: <BROADCAST,UP> mtu 1386 qdisc noqueue\\    link/ether {GATEWAY} brd ff:ff:ff:ff:ff:ff"
HOOK = Path(__file__).parents[1] / "dnsmasq-hook" / "update-client-ips.sh"


def _lease(expiry, mac, ip):
    return f"{expiry} {mac} {ip} * *"


class Recorder:
    """Stands in for subprocess.run and keeps each batch file's content."""

    def __init__(self, fail=False, link=LINK):
        self.calls = []
        self.fail = fail
        self.link = link

    def __call__(self, cmd, check=False, capture_output=False, text=False):
        if cmd[:3] == ["ip", "-o", "link"]:
            return SimpleNamespace(stdout=self.link)
        self.calls.append((cmd, Path(cmd[-1]).read_text()))
        if self.fail:
            raise subprocess.CalledProcessError(1, cmd)
        return SimpleNamespace(stdout="")


@pytest.mark.parametrize("link,per_lease", [(LINK, 2), ("", 1)])
def test_every_live_lease_is_pinned_in_one_batch(tmp_path, link, per_lease):
    leases = tmp_path / "vlan-wg.leases"
    leases.write_text(
        "\n".join(
            _lease(
                NOW + 60,
                f"02:00:00:00:{i // 256:02x}:{i % 256:02x}",
                f"192.0.2.{1 + i}",
            )
            for i in range(250)
        )
    )
    run = Recorder(link=link)

    assert lease_pins.main([str(leases)], run=run, now=NOW) == 0

    flows = [c for c in run.calls if c[0][0] == "ovs-ofctl"]
    assert len(flows) == 1
    assert flows[0][0][:3] == ["ovs-ofctl", "add-flows", "ovsbr0"]
    assert len(flows[0][1].splitlines()) == 250 * per_lease
    assert (
        "table=2,priority=100,ip,dl_src=02:00:00:00:00:3b,nw_src=192.0.2.60,actions=NORMAL"
        in flows[0][1].splitlines()
    )


@pytest.mark.parametrize("gateway", [GATEWAY, None])
def test_the_batch_writes_exactly_the_flows_the_dhcp_hook_writes(tmp_path, gateway):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    link = LINK if gateway else ""
    stubs = {
        "arp": "",
        "ovs-ofctl": f'echo "$*" >> {calls}',
        "ip": f"printf '%s\\n' '{link}'",
    }
    for tool, body in stubs.items():
        stub = bin_dir / tool
        stub.write_text(f"#!/bin/sh\n{body}\n")
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "DHCP_REPORTS_DIR": str(tmp_path / "queue"),
    }

    subprocess.run(
        ["sh", str(HOOK), "old", "52:54:00:2c:7a:ab", "192.0.2.75"], env=env, check=True
    )

    hook_flows = [
        line.split(" ", 2)[2]
        for line in calls.read_text().splitlines()
        if line.startswith("add-flow ovsbr0 ")
    ]
    assert hook_flows == lease_pins.pin_flows(
        "52:54:00:2c:7a:ab", "192.0.2.75", gateway
    )


def test_the_static_arp_entry_comes_with_the_pin():
    run = Recorder()

    lease_pins.pin([("52:54:00:2c:7a:13", "192.0.2.75")], run=run)

    neigh = [c for c in run.calls if c[0][:2] == ["ip", "-batch"]]
    assert neigh[0][1] == (
        "neigh replace 192.0.2.75 lladdr 52:54:00:2c:7a:13 dev vlan-wg nud permanent\n"
    )


def test_only_unexpired_ipv4_leases_count():
    text = "\n".join(
        [
            _lease(NOW + 60, "52:54:00:00:00:01", "192.0.2.1"),
            _lease(NOW - 1, "52:54:00:00:00:02", "192.0.2.2"),
            _lease(0, "52:54:00:00:00:03", "192.0.2.3"),
            "duid 00:01:00:01:2c:3b:4a:5d:52:54:00:00:00:04",
            _lease(NOW + 60, "52:54:00:00:00:05", "fd00::5"),
            _lease(NOW + 60, "52:54:00:00:00:01", "192.0.2.1"),
        ]
    )

    assert lease_pins.live_leases(text, NOW) == [
        ("52:54:00:00:00:01", "192.0.2.1"),
        ("52:54:00:00:00:03", "192.0.2.3"),
    ]


def test_a_malformed_lease_cannot_write_its_own_flow():
    text = "\n".join(
        [
            _lease(NOW + 60, "52:54:00:00:00:01,actions=drop", "192.0.2.1"),
            _lease(NOW + 60, "52:54:00:00:00:02", "192.0.2.2,actions=drop"),
            _lease(NOW + 60, "52:54:00:00:00:03", "192.0.2." + "256"),
            _lease(NOW + 60, "52:54:00:00:00:04", "192.0.2.4"),
        ]
    )

    assert lease_pins.live_leases(text, NOW) == [("52:54:00:00:00:04", "192.0.2.4")]


def test_an_uppercase_mac_is_pinned_as_openflow_prints_it():
    text = _lease(NOW + 60, "52:54:00:AB:CD:EF", "192.0.2.9")

    assert lease_pins.live_leases(text, NOW) == [("52:54:00:ab:cd:ef", "192.0.2.9")]


def test_no_leases_runs_nothing(tmp_path):
    leases = tmp_path / "vlan-wg.leases"
    leases.write_text("")
    run = Recorder()

    assert lease_pins.main([str(leases)], run=run, now=NOW) == 0
    assert run.calls == []


def test_a_failure_never_stops_the_vpn_from_starting(tmp_path):
    leases = tmp_path / "vlan-wg.leases"
    leases.write_text(_lease(NOW + 60, "52:54:00:00:00:01", "192.0.2.1"))

    assert lease_pins.main([str(leases)], run=Recorder(fail=True), now=NOW) == 0
    assert lease_pins.main([str(tmp_path / "missing")], run=Recorder(), now=NOW) == 0
