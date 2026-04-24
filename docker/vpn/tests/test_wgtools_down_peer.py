# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verify ``Wg.down_peer`` resolves the ofport before del-port, uses the
numeric ofport for del-flows (matching how flows were installed in
``up_peer``), and logs failures instead of silently capturing stderr.
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch


def test_down_peer_resolves_ofport_before_del_flows(wgtools_hyper, wgtools_module):
    peer = {"id": "hyper-old", "vpn": None}
    # check_output order:
    #   1) ovs-vsctl get interface ... ofport -> "42"
    #   2) ovs-vsctl del-port ... -> ""
    with patch.object(
        wgtools_module, "check_output", side_effect=["42", ""]
    ), patch.object(
        wgtools_module.subprocess,
        "run",
        return_value=MagicMock(returncode=0, stderr=""),
    ) as mock_run:
        wgtools_hyper.down_peer(peer, table="hypervisors")

        cmds = [" ".join(call.args[0]) for call in mock_run.call_args_list]
        del_flow_cmds = [c for c in cmds if "del-flows" in c]
        assert del_flow_cmds, "del-flows must be called"
        # The ofport is numeric (42), not the interface name.
        assert "in_port=42" in del_flow_cmds[0]
        assert "in_port=hyper-old" not in del_flow_cmds[0]


def test_down_peer_logs_del_flows_errors(wgtools_hyper, wgtools_module, caplog):
    peer = {"id": "hyper-old", "vpn": None}
    with patch.object(
        wgtools_module, "check_output", side_effect=["42", ""]
    ), patch.object(
        wgtools_module.subprocess,
        "run",
        return_value=MagicMock(returncode=1, stderr="ofctl: some error"),
    ):
        with caplog.at_level("WARNING"):
            wgtools_hyper.down_peer(peer, table="hypervisors")
        combined = caplog.text.lower()
        assert "del-flows" in combined
        assert "hyper-old" in combined


def test_down_peer_skips_del_flows_when_ofport_unresolved(
    wgtools_hyper, wgtools_module, caplog
):
    peer = {"id": "hyper-gone", "vpn": None}
    # First check_output (get ofport) raises; second (del-port) returns "".
    ofport_error = subprocess.CalledProcessError(1, "ovs-vsctl")

    def check_output_side_effect(*args, **kwargs):
        if not hasattr(check_output_side_effect, "called"):
            check_output_side_effect.called = True
            raise ofport_error
        return ""

    with patch.object(
        wgtools_module, "check_output", side_effect=check_output_side_effect
    ), patch.object(
        wgtools_module.subprocess,
        "run",
        return_value=MagicMock(returncode=0, stderr=""),
    ) as mock_run:
        with caplog.at_level("WARNING"):
            wgtools_hyper.down_peer(peer, table="hypervisors")
        # del-flows must be skipped when ofport cannot be resolved.
        del_flow_calls = [
            c for c in mock_run.call_args_list if "del-flows" in " ".join(c.args[0])
        ]
        assert not del_flow_calls
        assert "hyper-gone" in caplog.text


def test_down_peer_skips_del_flows_when_ofport_is_minus_one(
    wgtools_hyper, wgtools_module
):
    """An ofport of '-1' means the interface has no datapath port assigned;
    del-flows with 'in_port=-1' is meaningless and must be skipped."""
    peer = {"id": "hyper-nopd", "vpn": None}
    with patch.object(
        wgtools_module, "check_output", side_effect=["-1", ""]
    ), patch.object(
        wgtools_module.subprocess,
        "run",
        return_value=MagicMock(returncode=0, stderr=""),
    ) as mock_run:
        wgtools_hyper.down_peer(peer, table="hypervisors")

        del_flow_calls = [
            c for c in mock_run.call_args_list if "del-flows" in " ".join(c.args[0])
        ]
        assert not del_flow_calls
