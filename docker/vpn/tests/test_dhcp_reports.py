# SPDX-License-Identifier: AGPL-3.0-or-later
"""The dhcp hook queues its API reports; one warm worker sends new and recent leases first."""
from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest
from isardvdi_vpn import dhcp_reports

HOOK = Path(__file__).parents[1] / "dnsmasq-hook" / "update-client-ips.sh"


def _name(prio, stamp, action, mac, ip, pid=1):
    return f"{prio}.{stamp:012d}.{pid}.{action}.{mac.replace(':', '-')}.{ip}"


@pytest.fixture
def queue(tmp_path):
    q = tmp_path / "queue"
    q.mkdir()
    return q


def _queue(q, *names):
    for n in names:
        (q / n).write_text("")


def _leases(tmp_path, *entries):
    path = tmp_path / "vlan-wg.leases"
    path.write_text("".join(f"{exp} {mac} {ip} * *\n" for exp, mac, ip in entries))
    return str(path)


def test_a_new_lease_is_reported_before_the_replayed_ones(queue, tmp_path):
    _queue(
        queue,
        *[
            _name(1, i, "old", f"02:00:00:00:00:{i:02x}", f"192.0.2.{i}")
            for i in range(1, 50)
        ],
        _name(0, 99, "add", "52:54:00:2c:7a:13", "192.0.2.200"),
    )
    posted = []

    dhcp_reports.step(
        queue, _leases(tmp_path), post=lambda m, i: posted.append((m, i)) or 200
    )

    assert posted == [("52:54:00:2c:7a:13", "192.0.2.200")]


def test_replayed_leases_go_newest_first(queue, tmp_path):
    _queue(
        queue,
        _name(1, 1, "old", "02:00:00:00:00:01", "192.0.2.1"),
        _name(1, 2, "old", "02:00:00:00:00:02", "192.0.2.2"),
        _name(1, 3, "old", "02:00:00:00:00:03", "192.0.2.3"),
    )
    leases = _leases(
        tmp_path,
        (1000, "02:00:00:00:00:01", "192.0.2.1"),
        (3000, "02:00:00:00:00:02", "192.0.2.2"),
        (2000, "02:00:00:00:00:03", "192.0.2.3"),
    )
    posted = []

    while dhcp_reports.step(queue, leases, post=lambda m, i: posted.append(i) or 404):
        pass

    assert posted == ["192.0.2.2", "192.0.2.3", "192.0.2.1"]
    assert list(queue.iterdir()) == []


def test_only_the_latest_event_of_a_mac_is_reported(queue, tmp_path):
    _queue(
        queue,
        _name(1, 1, "old", "52:54:00:2c:7a:13", "192.0.2.10"),
        _name(1, 5, "old", "52:54:00:2c:7a:13", "192.0.2.11"),
    )
    posted = []

    dhcp_reports.step(
        queue, _leases(tmp_path), post=lambda m, i: posted.append(i) or 200
    )

    assert posted == ["192.0.2.11"]
    assert list(queue.iterdir()) == []


@pytest.mark.parametrize("status", [500, 503, 401, 429])
def test_a_transient_failure_keeps_the_event(queue, tmp_path, monkeypatch, status):
    monkeypatch.setattr(dhcp_reports, "RETRY_SECONDS", 0)
    _queue(queue, _name(0, 1, "add", "52:54:00:2c:7a:13", "192.0.2.10"))

    dhcp_reports.step(queue, _leases(tmp_path), post=lambda m, i: status)

    assert len(list(queue.iterdir())) == 1


def test_an_unreachable_api_keeps_the_event(queue, tmp_path, monkeypatch):
    monkeypatch.setattr(dhcp_reports, "RETRY_SECONDS", 0)
    _queue(queue, _name(0, 1, "add", "52:54:00:2c:7a:13", "192.0.2.10"))

    def down(mac, ip):
        raise ConnectionError("api down")

    dhcp_reports.step(queue, _leases(tmp_path), post=down)

    assert len(list(queue.iterdir())) == 1


def test_a_stopped_desktop_is_dropped_not_retried(queue, tmp_path):
    _queue(queue, _name(1, 1, "old", "52:54:00:2c:7a:13", "192.0.2.10"))

    dhcp_reports.step(queue, _leases(tmp_path), post=lambda m, i: 404)

    assert list(queue.iterdir()) == []


def test_half_written_and_foreign_files_are_ignored(queue, tmp_path):
    _queue(
        queue,
        ".1.000000000001.1.old.52-54-00-2c-7a-ab.192.0.2.10",
        "README",
        "1.x.1.old.a.b",
    )

    assert dhcp_reports.step(queue, _leases(tmp_path), post=lambda m, i: 200) is False


@pytest.fixture
def hook_env(tmp_path, queue):
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    calls = tmp_path / "calls"
    for tool in ("arp", "ovs-ofctl", "python3"):
        stub = bin_dir / tool
        stub.write_text(f'#!/bin/sh\necho "{tool} $*" >> {calls}\n')
        stub.chmod(stub.stat().st_mode | stat.S_IEXEC)
    silent_ip = bin_dir / "ip"
    silent_ip.write_text("#!/bin/sh\n")
    silent_ip.chmod(silent_ip.stat().st_mode | stat.S_IEXEC)
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "DHCP_REPORTS_DIR": str(queue),
    }
    return env, calls


@pytest.mark.parametrize("action,prio", [("add", "0"), ("old", "1")])
def test_the_hook_pins_then_queues_without_calling_the_api(
    hook_env, queue, action, prio
):
    env, calls = hook_env

    subprocess.run(
        ["sh", str(HOOK), action, "52:54:00:2c:7a:13", "192.0.2.10", "slax"],
        env=env,
        check=True,
    )

    assert calls.read_text().splitlines() == [
        "arp -s 192.0.2.10 52:54:00:2c:7a:13 dev vlan-wg",
        "ovs-ofctl add-flow ovsbr0 table=2,priority=100,ip,dl_src=52:54:00:2c:7a:13,nw_src=192.0.2.10,actions=NORMAL",
    ]
    queued = [dhcp_reports.parse(p.name) for p in queue.iterdir()]
    assert [(e["prio"], e["action"], e["mac"], e["ip"]) for e in queued] == [
        (int(prio), action, "52:54:00:2c:7a:13", "192.0.2.10")
    ]


def test_a_released_lease_is_not_queued(hook_env, queue):
    env, _ = hook_env

    subprocess.run(
        ["sh", str(HOOK), "del", "52:54:00:2c:7a:13", "192.0.2.10"], env=env, check=True
    )

    assert list(queue.iterdir()) == []
