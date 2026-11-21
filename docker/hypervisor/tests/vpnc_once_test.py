# SPDX-License-Identifier: AGPL-3.0-or-later
"""isardvdi-hypervisor-vpnc --once: the watchdog's config re-fetch and recovery."""
from unittest.mock import mock_open, patch

from isardvdi_hypervisor import vpnc


def test_once_reconnects_when_the_config_changed():
    calls = []
    with patch.object(
        vpnc, "_fetch_peer_content", return_value="NEWCONF"
    ), patch.object(
        vpnc, "connect", lambda c: calls.append(("connect", c))
    ), patch.object(
        vpnc, "check_call", lambda cmd, *a, **k: calls.append(tuple(cmd))
    ), patch(
        "builtins.open", mock_open(read_data="OLDCONF")
    ):
        assert vpnc.run_once() == 0
    assert calls == [("connect", "NEWCONF")]  # reconnected, never a bare down/up


def test_once_bounces_wg0_when_the_config_is_unchanged():
    calls = []
    with patch.object(vpnc, "_fetch_peer_content", return_value="SAME"), patch.object(
        vpnc, "connect", lambda c: calls.append("connect")
    ), patch.object(
        vpnc, "check_call", lambda cmd, *a, **k: calls.append(tuple(cmd))
    ), patch(
        "builtins.open", mock_open(read_data="SAME")
    ):
        assert vpnc.run_once() == 0
    assert "connect" not in calls  # unchanged config is not rewritten
    assert any("down" in c for c in calls) and any("up" in c for c in calls)


def test_once_exits_1_when_the_api_is_unreachable():
    calls = []
    with patch.object(
        vpnc, "_fetch_peer_content", side_effect=RuntimeError("api down")
    ), patch.object(vpnc, "connect", lambda c: calls.append("connect")), patch.object(
        vpnc, "check_call", lambda *a, **k: calls.append("check_call")
    ):
        assert vpnc.run_once() == 1
    assert calls == []  # nothing touched, and no retry loop
