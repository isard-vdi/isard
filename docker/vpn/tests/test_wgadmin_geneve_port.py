# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verify ``ensure_geneve_port`` sets up a geneve hypervisor idempotently.

In geneve-only the OVS BFD session is the only liveness signal: tunnel_monitor
reads ``bfd_status:state`` and publishes ``vpn.tunnel_status`` from it. Setting
BFD only when the port was just created left an already-present port without a
BFD session, so ``bfd_status`` stayed empty and the tunnel read as down forever.
The flows have the same problem for a different reason -- they live in
ovs-vswitchd, not the OVS db, so they do not survive a restart.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from isardvdi_vpn import wgadmin


class FakeOvs:
    """Port table of one bridge, driven through subprocess.run/check_output."""

    def __init__(self, ports):
        self.ports = {n: {"options:remote_ip": ip} for n, ip in ports.items()}
        self.flows = []
        self.ops = []

    def run(self, cmd, **kwargs):
        assert cmd[1] == "--timeout=5", cmd
        cmd = [cmd[0]] + cmd[2:]
        if cmd[0] == "ovs-ofctl":
            self.ops.append(cmd[1])
            if cmd[1] == "add-flow":
                self.flows.append(cmd[3])
            return
        if cmd[1:3] == ["--may-exist", "add-port"]:
            self.ops.append("add-port")
            port = self.ports.setdefault(cmd[4], {})
            port.update(a.split("=", 1) for a in cmd[9:])
        elif cmd[1:3] == ["--if-exists", "del-port"]:
            self.ops.append("del-port")
            self.ports.pop(cmd[3], None)
        else:
            raise AssertionError(f"unexpected {cmd}")

    def check_output(self, cmd, **kwargs):
        assert cmd[1] == "--timeout=5", cmd
        cmd = (cmd[0],) + tuple(cmd[2:])
        assert cmd[1] == "get" and cmd[4] == "ofport", cmd
        return str(list(self.ports).index(cmd[3]) + 1)

    def patched(self, module):
        from contextlib import ExitStack

        stack = ExitStack()
        stack.enter_context(patch.object(module.subprocess, "run", self.run))
        stack.enter_context(patch.object(module, "check_output", self.check_output))
        return stack


def _calls(mock):
    return [tuple(c.args[0]) for c in mock.call_args_list]


@pytest.fixture
def geneve_env(monkeypatch):
    monkeypatch.setenv("WG_HYPERS_PORT", "4443")
    monkeypatch.setattr(
        wgadmin.socket, "gethostbyname", lambda h: "10.0.0.9", raising=False
    )
    return wgadmin


def test_creates_port_and_enables_bfd_when_missing(geneve_env):
    with patch.object(geneve_env, "check_output", return_value="") as co, patch.object(
        geneve_env, "subprocess"
    ) as sp:
        assert geneve_env.ensure_geneve_port("isard-hypervisor", "hyper.local") is True
    cmds = _calls(sp.run)
    assert any("add-port" in c for c in cmds)
    assert any("bfd:enable=true" in c for c in cmds)


def test_enables_bfd_even_when_port_already_exists(geneve_env):
    """A pre-existing port must still get its BFD session and flows."""
    ovs = FakeOvs({"isard-hypervisor": "192.0.2.30"})
    with ovs.patched(geneve_env):
        assert geneve_env.ensure_geneve_port("isard-hypervisor", "hyper.local") is True
    assert ovs.ports["isard-hypervisor"]["bfd:enable"] == "true"
    assert ovs.flows, "flows must be re-applied after restart"


def test_unresolvable_hostname_is_skipped(geneve_env):
    import socket as _socket

    def boom(_h):
        raise _socket.gaierror()

    with patch.object(geneve_env.socket, "gethostbyname", boom), patch.object(
        geneve_env, "subprocess"
    ) as sp:
        assert geneve_env.ensure_geneve_port("isard-hypervisor", "nope.local") is False
    assert not sp.run.call_args_list


def test_missing_id_or_hostname_is_skipped(geneve_env):
    with patch.object(geneve_env, "subprocess") as sp:
        assert geneve_env.ensure_geneve_port("isard-hypervisor", None) is False
        assert geneve_env.ensure_geneve_port(None, "hyper.local") is False
    assert not sp.run.call_args_list


def test_existing_port_follows_the_hypervisor_address(geneve_env, monkeypatch):
    """Same id, new address: the port is kept and its remote_ip moved."""
    ovs = FakeOvs({"isard-hypervisor": "192.0.2.10"})
    monkeypatch.setattr(geneve_env.socket, "gethostbyname", lambda h: "192.0.2.20")
    with ovs.patched(geneve_env):
        assert geneve_env.ensure_geneve_port("isard-hypervisor", "hyper.local") is True
    assert ovs.ports["isard-hypervisor"]["options:remote_ip"] == "192.0.2.20"
    assert list(ovs.ports) == ["isard-hypervisor"]


def test_port_of_an_id_that_prefixes_another_is_created(geneve_env):
    """An existing "hyp10" must not make "hyp1" look present."""
    ovs = FakeOvs({"hyp10": "192.0.2.10"})
    with ovs.patched(geneve_env):
        assert geneve_env.ensure_geneve_port("hyp1", "hyper.local") is True
    assert set(ovs.ports) == {"hyp1", "hyp10"}
    assert ovs.ports["hyp10"]["options:remote_ip"] == "192.0.2.10"


def test_removed_hypervisor_is_not_recreated_by_the_monitor(geneve_env, monkeypatch):
    """The monitor read the row before the delete: its ensure re-reads the row
    under the port lock and must not bring the port back."""
    ovs = FakeOvs({"isard-hypervisor": "192.0.2.40"})
    rows = {"isard-hypervisor": {"hostname": "hyper.local"}}
    monkeypatch.setattr(
        geneve_env,
        "_registered_hostname",
        lambda h: (rows.get(h) or {}).get("hostname"),
    )
    with ovs.patched(geneve_env):
        del rows["isard-hypervisor"]
        geneve_env.remove_geneve_port("isard-hypervisor")
        assert (
            geneve_env.ensure_registered_geneve_port("isard-hypervisor", "hyper.local")
            is False
        )
    assert ovs.ports == {}


def test_monitor_ensure_and_delete_do_not_interleave(geneve_env, monkeypatch):
    """A monitor tick racing the delete event: whichever takes the lock first
    finishes before the other starts, so the port never outlives its row."""
    import threading

    ovs = FakeOvs({})
    rows = {"isard-hypervisor": {"hostname": "hyper.local"}}
    in_ensure = threading.Event()
    release = threading.Event()

    def registered(h):
        hostname = (rows.get(h) or {}).get("hostname")
        in_ensure.set()
        release.wait(5)
        return hostname

    monkeypatch.setattr(geneve_env, "_registered_hostname", registered)
    with ovs.patched(geneve_env):
        tick = threading.Thread(
            target=geneve_env.ensure_registered_geneve_port, args=("isard-hypervisor",)
        )
        tick.start()
        assert in_ensure.wait(5)
        rows.clear()
        delete = threading.Thread(
            target=geneve_env.remove_geneve_port, args=("isard-hypervisor",)
        )
        delete.start()
        delete.join(0.2)
        assert delete.is_alive(), "the delete must wait for the ensure in progress"
        release.set()
        tick.join(5)
        delete.join(5)
    assert ovs.ports == {}
    assert ovs.ops.index("add-port") < ovs.ops.index("del-port")


def test_monitor_is_handed_the_port_creator(monkeypatch):
    """The changefeed and the start pass resolve the hostname once; the
    monitor is what retries, so it must get the function that creates ports."""
    started = {}
    monkeypatch.setattr(
        wgadmin.tunnel_monitor, "start", lambda **kw: started.update(kw)
    )
    monkeypatch.setattr(wgadmin, "start_monitoring_vpn_status", lambda: None)
    monkeypatch.setattr(wgadmin.dhcp_reports, "start", lambda: None)

    class _Stop(Exception):
        pass

    def stop(*a, **k):
        raise _Stop()

    monkeypatch.setattr(wgadmin.log, "info", stop)
    with pytest.raises(_Stop):
        wgadmin.main()
    assert started.get("ensure_port") is wgadmin.ensure_registered_geneve_port
