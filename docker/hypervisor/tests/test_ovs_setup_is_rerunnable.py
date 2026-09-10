# SPDX-License-Identifier: AGPL-3.0-or-later

"""``setup.sh`` must survive being run twice against the same OVS database.

Same failure as on the VPN side: the OVS database lives in the container's own
writable layer, so ``docker restart isard-hypervisor`` keeps it and every
``ovs-vsctl add-port`` fails on the second start — taking the geneve
``remote_ip`` and ``dst_port`` of the tunnel with it.

The script runs for real against stubs that model OVS's duplicate semantics.
Both tunnelling modes are exercised, because they add different ports.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "src" / "ovs" / "setup.sh"

STUB_OVS_VSCTL = r"""#!/bin/sh
STATE="$STUB_STATE"
echo "ovs-vsctl $*" >> "$STATE/calls"
MAY_EXIST=no
[ "$1" = "--may-exist" ] && { MAY_EXIST=yes; shift; }
case "$1" in
  add-br)
    BR="$2"
    if [ -e "$STATE/br-$BR" ] && [ "$MAY_EXIST" = no ]; then
      echo "ovs-vsctl: cannot create a bridge named $BR because a bridge named $BR already exists" >&2
      exit 1
    fi
    touch "$STATE/br-$BR"
    ;;
  add-port)
    PORT="$3"
    if [ -e "$STATE/port-$PORT" ] && [ "$MAY_EXIST" = no ]; then
      echo "ovs-vsctl: cannot create a port named $PORT because a port named $PORT already exists on bridge $2" >&2
      exit 1
    fi
    touch "$STATE/port-$PORT"
    ;;
  get)
    case "$*" in
      *bfd_status:state*) echo up ;;
      *) echo 1 ;;
    esac
    ;;
esac
exit 0
"""

STUB_RECORD = '#!/bin/sh\necho "$(basename "$0") $*" >> "$STUB_STATE/calls"\nexit 0\n'


def _write(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


@pytest.fixture
def ovs_env(tmp_path):
    bindir = tmp_path / "bin"
    bindir.mkdir()
    state = tmp_path / "state"
    state.mkdir()

    _write(bindir / "ovs-vsctl", STUB_OVS_VSCTL)
    for name in ("ovs-ofctl", "ip", "ovsdb-server", "ovs-vswitchd", "ovsdb-tool"):
        _write(bindir / name, STUB_RECORD)
    _write(bindir / "sleep", "#!/bin/sh\nexit 0\n")

    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "STUB_STATE": str(state),
        "API_DOMAIN": "api.example",
        "WG_GUESTS_NETS": "10.2.0.0/16",
        "WG_HYPERS_NET": "10.1.0.0/24",
        "WG_USERS_NET": "10.0.0.0/16",
        "WG_HYPERS_GW": "10.1.0.1",
        "DOMAIN": "hyper-1",
        "DOCKER_NET": "172.31.255",
        "HYPERVISOR_HOST_TRUNK_INTERFACE": "vlans",
    }
    return {"env": env, "state": state}


def _run(ovs_env, mode):
    env = {**ovs_env["env"], "HYPERVISOR_VPN_TUNNELING_MODE": mode}
    if mode == "geneve":
        env["VPN_DOMAIN"] = "10.9.9.9"
    return subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60
    )


def _add_port_calls(ovs_env):
    path = ovs_env["state"] / "calls"
    lines = path.read_text().splitlines() if path.exists() else []
    return [c for c in lines if " add-port " in c]


@pytest.mark.parametrize("mode", ["geneve", "wireguard"])
def test_the_second_run_adds_no_port_without_may_exist(ovs_env, mode):
    _run(ovs_env, mode)
    (ovs_env["state"] / "calls").unlink(missing_ok=True)
    second = _run(ovs_env, mode)

    offenders = [c for c in _add_port_calls(ovs_env) if "--may-exist" not in c]
    assert (
        offenders == []
    ), f"these add-port calls would fail on a container restart: {offenders}"
    assert "already exists" not in second.stderr


@pytest.mark.parametrize("mode", ["geneve", "wireguard"])
def test_every_port_is_still_added_on_a_first_run(ovs_env, mode):
    _run(ovs_env, mode)
    assert _add_port_calls(ovs_env), "the script added no port at all"
