# SPDX-License-Identifier: AGPL-3.0-or-later

"""``ovs_setup.sh`` must survive being run twice against the same OVS database.

The database lives at ``/etc/openvswitch/conf.db`` inside the container's own
writable layer, not on a volume, so ``docker restart isard-vpn`` keeps it. On
that second start every ``ovs-vsctl add-port`` used to fail with "a port named
X already exists", and with it the ``-- set interface`` clauses that carry the
geneve ``remote_ip`` and the ``vlan-wg`` ``type=internal``.

The script runs for real here, against stubs that model OVS's own duplicate
semantics: ``add-port`` on an existing port fails unless ``--may-exist`` is
given.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "ovs" / "ovs_setup.sh"

STUB_OVS_VSCTL = r"""#!/bin/sh
# Models the subset of ovs-vsctl the setup script uses, including the
# duplicate-port refusal that --may-exist suppresses.
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
    # Everything after the first `--` is a follow-up command in the same
    # transaction; record it so the test can see it was (re)applied.
    while [ $# -gt 0 ]; do
      if [ "$1" = "--" ]; then shift; echo "$*" >> "$STATE/set-$PORT"; break; fi
      shift
    done
    ;;
  get) echo 1 ;;
esac
exit 0
"""

STUB_TRUE = "#!/bin/sh\nexit 0\n"
STUB_RECORD = '#!/bin/sh\necho "$(basename "$0") $*" >> "$STUB_STATE/calls"\nexit 0\n'


def _write(path: Path, body: str) -> None:
    path.write_text(body)
    path.chmod(0o755)


@pytest.fixture
def ovs_env(tmp_path):
    """A PATH of stubs plus the environment ``ovs_setup.sh`` reads."""
    bindir = tmp_path / "bin"
    bindir.mkdir()
    state = tmp_path / "state"
    state.mkdir()

    _write(bindir / "ovs-vsctl", STUB_OVS_VSCTL)
    for name in ("ovs-ofctl", "ip", "ovsdb-server", "ovs-vswitchd", "ovsdb-tool"):
        _write(bindir / name, STUB_RECORD)
    _write(bindir / "sleep", STUB_TRUE)

    env = {
        **os.environ,
        "PATH": f"{bindir}:{os.environ['PATH']}",
        "STUB_STATE": str(state),
        "API_DOMAIN": "api.example",
        "WG_GUESTS_NETS": "10.2.0.0/16",
        "WG_USERS_NET": "10.0.0.0/16",
        "WG_HYPERS_NET": "10.1.0.0/16",
        "WG_MAIN_NET": "10.0.0.0/8",
        "DOCKER_NET": "172.31.255",
        "HYPERVISOR_HOST_TRUNK_INTERFACE": "vlans",
    }
    return {"env": env, "state": state, "root": tmp_path}


def _run(ovs_env):
    env = dict(ovs_env["env"])
    # The script writes to absolute paths (/etc/openvswitch, /var/log/ovs);
    # unprivileged those writes just fail, which is not what is under test.
    return subprocess.run(
        ["bash", str(SCRIPT)],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def _calls(ovs_env):
    path = ovs_env["state"] / "calls"
    return path.read_text().splitlines() if path.exists() else []


def _add_port_calls(ovs_env):
    return [c for c in _calls(ovs_env) if " add-port " in c]


class TestEveryPortIsAddedIdempotently:
    def test_the_second_run_adds_no_port_without_may_exist(self, ovs_env):
        _run(ovs_env)
        (ovs_env["state"] / "calls").unlink(missing_ok=True)
        second = _run(ovs_env)

        offenders = [c for c in _add_port_calls(ovs_env) if "--may-exist" not in c]
        assert offenders == [], (
            "these add-port calls would fail on a container restart: " f"{offenders}"
        )
        assert "already exists" not in second.stderr

    def test_the_trunk_port_is_not_reported_as_added_when_it_failed(self, ovs_env):
        # Make every ovs-vsctl fail, the way a broken OVS would.
        _write(
            ovs_env["root"] / "bin" / "ovs-vsctl",
            '#!/bin/sh\necho "ovs-vsctl: boom" >&2\nexit 1\n',
        )
        out = _run(ovs_env)
        combined = out.stdout + out.stderr

        assert "trunk interface vlans added to OVS bridge" not in combined
        assert "Could not add VPN trunk interface vlans" in combined
