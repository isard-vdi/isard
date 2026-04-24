# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verify ``Wg.up_peer`` applies BFD + VLAN 4095 flow rules on geneve-only
hypervisor ports in BOTH the new-port and existing-port branches.

Previously, a fresh hypervisor only had ``ovs-vsctl add-port`` executed,
leaving it without BFD or the VLAN 4095 / VM MAC OUI flow rules — breaking
the security policy. These tests lock in the refactor.
"""
from __future__ import annotations

from unittest.mock import patch


def test_up_peer_new_geneve_port_adds_bfd_and_flows(wgtools_hyper, wgtools_module):
    peer = {"id": "hyper-new", "hostname": "hyper-new.lan", "vpn": None}
    # check_output order:
    #   1) ovs-vsctl show -> peer not in it (empty)
    #   2) ovs-vsctl get interface ... ofport -> "42"
    with patch.object(
        wgtools_module, "check_output", side_effect=["", "42"]
    ), patch.object(wgtools_module.subprocess, "run") as mock_run, patch.object(
        wgtools_module.socket, "gethostbyname", return_value="10.0.0.1"
    ):
        assert wgtools_hyper.up_peer(peer) is True

        cmds = [" ".join(call.args[0]) for call in mock_run.call_args_list]

        # add-port with type=geneve and the resolved remote_ip must be issued.
        add_port_cmds = [c for c in cmds if "add-port" in c]
        assert len(add_port_cmds) == 1
        assert "type=geneve" in add_port_cmds[0]
        assert "options:remote_ip=10.0.0.1" in add_port_cmds[0]

        # BFD must be enabled even on the fresh-port path.
        assert any("bfd:enable=true" in c for c in cmds)

        # All 4 flow rules (priorities 451/451/450/449) must be installed,
        # keyed off the numeric ofport "42".
        flow_cmds = [c for c in cmds if "add-flow" in c]
        assert len(flow_cmds) == 4
        assert all("in_port=42" in c for c in flow_cmds)
        assert any("priority=451,arp" in c for c in flow_cmds)
        assert any("priority=451,udp" in c for c in flow_cmds)
        assert any("priority=450,ip" in c for c in flow_cmds)
        assert any("priority=449" in c and "actions=drop" in c for c in flow_cmds)


def test_up_peer_existing_geneve_port_adds_bfd_and_flows(wgtools_hyper, wgtools_module):
    peer = {"id": "hyper-existing", "hostname": "hyper.lan", "vpn": None}
    with patch.object(
        wgtools_module,
        "check_output",
        side_effect=["Port hyper-existing ...", "42"],
    ), patch.object(wgtools_module.subprocess, "run") as mock_run, patch.object(
        wgtools_module.socket, "gethostbyname", return_value="10.0.0.2"
    ):
        assert wgtools_hyper.up_peer(peer) is True

        cmds = [" ".join(call.args[0]) for call in mock_run.call_args_list]

        # Existing port path uses `set interface ... options:remote_ip=...`,
        # not add-port.
        assert not any("add-port" in c for c in cmds)
        assert any("set" in c and "options:remote_ip=10.0.0.2" in c for c in cmds)

        assert any("bfd:enable=true" in c for c in cmds)
        flow_cmds = [c for c in cmds if "add-flow" in c]
        assert len(flow_cmds) == 4
        assert all("in_port=42" in c for c in flow_cmds)


def test_up_peer_returns_false_on_unresolvable_hostname(wgtools_hyper, wgtools_module):
    import socket as _socket

    peer = {"id": "hyper-bad", "hostname": "nope.invalid", "vpn": None}
    with patch.object(
        wgtools_module.socket, "gethostbyname", side_effect=_socket.gaierror
    ), patch.object(wgtools_module.subprocess, "run") as mock_run:
        assert wgtools_hyper.up_peer(peer) is False
        assert mock_run.call_count == 0


def test_up_peer_wg_geneve_installs_flows_on_fresh_port(wgtools_hyper, wgtools_module):
    """Regression: when the OVS port is added for the first time on the
    WG+geneve path, BFD + VLAN-4095 flow rules must also be installed
    (not only when the port already exists)."""
    peer = {
        "id": "hyper-new",
        "hostname": "hyper-new.internal",
        "vpn": {
            "wireguard": {
                "Address": "10.0.0.42",
                "keys": {"public": "pk"},
                "extra_client_nets": None,
                "AllowedIPs": "0.0.0.0/0",
            }
        },
    }
    # check_output order on the fresh-port branch:
    #   1) ovs-vsctl show -> peer not in it (empty)
    #   2) ovs-vsctl get Interface ... ofport -> "42"
    with patch.object(
        wgtools_module, "check_output", side_effect=["", "42"]
    ), patch.object(wgtools_module.subprocess, "run") as mock_run:
        assert wgtools_hyper.up_peer(peer) is True

        cmds = [" ".join(call.args[0]) for call in mock_run.call_args_list]

        # add-port with type=geneve and the remote_ip must be issued.
        add_port_cmds = [c for c in cmds if "add-port" in c]
        assert len(add_port_cmds) == 1
        assert "type=geneve" in add_port_cmds[0]
        assert "options:remote_ip=10.0.0.42" in add_port_cmds[0]

        # BFD must be enabled even on the fresh-port path.
        assert any("bfd:enable=true" in c for c in cmds)

        # All 4 flow rules (priorities 451/451/450/449) must be installed.
        flow_cmds = [c for c in cmds if "add-flow" in c]
        assert len(flow_cmds) == 4
        assert all("in_port=42" in c for c in flow_cmds)
        assert any("priority=451,arp" in c for c in flow_cmds)
        assert any("priority=451,udp" in c for c in flow_cmds)
        assert any("priority=450,ip" in c for c in flow_cmds)
        assert any("priority=449" in c and "actions=drop" in c for c in flow_cmds)


def test_up_peer_wg_geneve_installs_flows_on_existing_port(
    wgtools_hyper, wgtools_module
):
    """Existing-port branch on the WG+geneve path must continue to
    install BFD + VLAN-4095 flow rules (parity with the fresh-port
    branch after the lift-out refactor)."""
    peer = {
        "id": "hyper-existing",
        "hostname": "hyper-existing.internal",
        "vpn": {
            "wireguard": {
                "Address": "10.0.0.43",
                "keys": {"public": "pk"},
                "extra_client_nets": None,
                "AllowedIPs": "0.0.0.0/0",
            }
        },
    }
    with patch.object(
        wgtools_module,
        "check_output",
        side_effect=["Port hyper-existing ...", "42"],
    ), patch.object(wgtools_module.subprocess, "run") as mock_run:
        assert wgtools_hyper.up_peer(peer) is True

        cmds = [" ".join(call.args[0]) for call in mock_run.call_args_list]

        # Existing-port path uses `set interface ... options:remote_ip=...`
        # rather than add-port.
        assert not any("add-port" in c for c in cmds)
        assert any("set" in c and "options:remote_ip=10.0.0.43" in c for c in cmds)

        assert any("bfd:enable=true" in c for c in cmds)
        flow_cmds = [c for c in cmds if "add-flow" in c]
        assert len(flow_cmds) == 4
        assert all("in_port=42" in c for c in flow_cmds)
        # Legacy p201/p200 rules should be gone (superseded by p450/p449).
        assert not any("priority=201" in c for c in flow_cmds)
        assert not any("priority=200" in c for c in flow_cmds)
