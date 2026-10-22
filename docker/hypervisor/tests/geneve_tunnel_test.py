"""geneve-tunnel.sh against fake ovs-vsctl, ovs-ofctl and getent, VPN up or not at boot."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "src" / "ovs" / "geneve-tunnel.sh"

pytestmark = pytest.mark.skipif(shutil.which("sh") is None, reason="needs sh")

FAKE = Path(__file__).resolve().parent / "fake_ovs_tools.py"


@pytest.fixture
def fake_ovs(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    fake = FAKE
    for tool in ("getent", "ovs-vsctl", "ovs-ofctl"):
        wrapper = bindir / tool
        wrapper.write_text(f'#!/bin/sh\nexec "{sys.executable}" "{fake}" {tool} "$@"\n')
        wrapper.chmod(0o755)
    state = {"hosts": {}, "port": None, "flows": [], "calls": []}
    (tmp_path / "state.json").write_text(json.dumps(state))

    class Fake:
        def state(self):
            return json.loads((tmp_path / "state.json").read_text())

        def set(self, **kw):
            st = self.state()
            st.update(kw)
            (tmp_path / "state.json").write_text(json.dumps(st))

        def run(self, *args):
            env = dict(os.environ)
            env.update(
                PATH=f"{bindir}:{env['PATH']}",
                FAKE_STATE=str(tmp_path),
                VPN_DOMAIN="isard-vpn",
                WG_HYPERS_PORT="4443",
                WG_GUESTS_NETS="10.2.0.0/16",
            )
            return subprocess.run(
                ["sh", str(SCRIPT), *args],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )

    return Fake()


def _flows(fake):
    return fake.state()["flows"]


def test_vpn_not_up_yet_fails_without_creating_anything(fake_ovs):
    res = fake_ovs.run("ensure", "0")
    assert res.returncode == 1
    assert fake_ovs.state()["port"] is None
    assert _flows(fake_ovs) == []


def test_waits_for_the_vpn_to_resolve(fake_ovs):
    """The boot race: isard-vpn appears a moment after the hypervisor."""
    import threading
    import time

    def vpn_comes_up():
        time.sleep(1)
        fake_ovs.set(hosts={"isard-vpn": "192.0.2.10"})

    t = threading.Thread(target=vpn_comes_up)
    t.start()
    res = fake_ovs.run("ensure", "20")
    t.join()
    assert res.returncode == 0, res.stderr
    assert "GENEVE_PORT=5" in res.stdout
    assert fake_ovs.state()["port"]["options:remote_ip"] == "192.0.2.10"


def test_creates_port_bfd_and_ingress_flows(fake_ovs):
    fake_ovs.set(hosts={"isard-vpn": "192.0.2.10"})
    res = fake_ovs.run("ensure")
    assert res.returncode == 0, res.stderr
    port = fake_ovs.state()["port"]
    assert port["bfd:enable"] == "true"
    flows = _flows(fake_ovs)
    assert any(f.startswith("priority=211,in_port=5,dl_vlan=4095") for f in flows)
    assert any(
        "priority=220,udp,in_port=5" in f and "nw_src=10.2.0.1" in f for f in flows
    )
    assert sum(f.startswith("priority=212,arp,in_port=5") for f in flows) == 4


def test_second_run_changes_nothing(fake_ovs):
    """The maintenance loop runs it every minute: in steady state it must not
    touch the port or reinstall the flows."""
    fake_ovs.set(hosts={"isard-vpn": "192.0.2.10"})
    assert fake_ovs.run("ensure").returncode == 0
    before = len(_flows(fake_ovs))
    seen = len(fake_ovs.state()["calls"])
    res = fake_ovs.run("ensure")
    assert res.returncode == 0
    assert len(_flows(fake_ovs)) == before
    new_calls = fake_ovs.state()["calls"][seen:]
    assert not any("add-port" in c for c in new_calls)
    assert not any("add-flow" in c for c in new_calls)
    assert res.stderr == "", "a steady-state run must be silent"


def test_follows_the_vpn_to_a_new_address(fake_ovs):
    fake_ovs.set(hosts={"isard-vpn": "192.0.2.10"})
    assert fake_ovs.run("ensure").returncode == 0
    fake_ovs.set(hosts={"isard-vpn": "192.0.2.20"})
    assert fake_ovs.run("ensure").returncode == 0
    assert fake_ovs.state()["port"]["options:remote_ip"] == "192.0.2.20"


def test_missing_flows_are_put_back(fake_ovs):
    fake_ovs.set(hosts={"isard-vpn": "192.0.2.10"})
    assert fake_ovs.run("ensure").returncode == 0
    fake_ovs.set(flows=[])
    assert fake_ovs.run("ensure").returncode == 0
    assert any(f.startswith("priority=211,in_port=5") for f in _flows(fake_ovs))


def test_flows_action_for_wireguard_mode(fake_ovs):
    res = fake_ovs.run("flows", "3")
    assert res.returncode == 0, res.stderr
    assert fake_ovs.state()["port"] is None
    assert any(f.startswith("priority=211,in_port=3") for f in _flows(fake_ovs))
