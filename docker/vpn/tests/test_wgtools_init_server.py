# SPDX-License-Identifier: AGPL-3.0-or-later
"""``init_server`` must not call wg-quick through the path the host AppArmor
profile is attached to, must not tear down an interface that is not there, and
must surface the reason wg-quick refused instead of only its exit status.
"""
from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

import pytest


def _init_server(wgtools_module, wg, *, iface_present, up_rc=0, up_stderr=""):
    """Run init_server against a fake that answers by argv, not by call order.

    Answering by order would make the pre-fix code fail on an exhausted mock
    rather than on the assertion, which proves nothing about behaviour.
    """
    wg.server_ip = "10.1.0.1"
    wg.server_mask = "24"
    wg.server_port = "4460"
    wg.keys = MagicMock(skeys={"private": "k"})

    def fake_run(argv, *args, **kwargs):
        argv = list(argv)
        if argv[:1] == ["ip"]:
            return MagicMock(returncode=0 if iface_present else 1, stderr="")
        if "up" in argv:
            return MagicMock(returncode=up_rc, stderr=up_stderr)
        return MagicMock(returncode=0, stderr="")

    with patch.object(
        wgtools_module.subprocess, "run", side_effect=fake_run
    ) as mock_run:
        with patch("builtins.open", MagicMock()):
            wg.init_server()
    return mock_run


def _cmds(mock_run):
    return [list(call.args[0]) for call in mock_run.call_args_list]


def test_wg_quick_is_not_called_through_the_profiled_path(
    wgtools_module, wgtools_hyper
):
    mock_run = _init_server(wgtools_module, wgtools_hyper, iface_present=False)
    called = [c for c in _cmds(mock_run) if any("wg-quick" in a for a in c)]
    assert called, "wg-quick must be invoked"
    for cmd in called:
        assert cmd[0] == "/isard/bin/wg-quick", cmd
        assert cmd[0] != "/usr/bin/wg-quick"


def test_down_is_skipped_when_the_interface_is_absent(wgtools_module, wgtools_hyper):
    # `ip address show` non-zero -> nothing to bring down.
    mock_run = _init_server(wgtools_module, wgtools_hyper, iface_present=False)
    assert not [c for c in _cmds(mock_run) if "down" in c], _cmds(mock_run)


def test_down_still_runs_when_the_interface_is_present(wgtools_module, wgtools_hyper):
    mock_run = _init_server(wgtools_module, wgtools_hyper, iface_present=True)
    assert [c for c in _cmds(mock_run) if "down" in c], _cmds(mock_run)


def test_a_refusing_wg_quick_reports_its_stderr_and_names_apparmor(
    wgtools_module, wgtools_hyper
):
    stderr = "/isard/bin/wg-quick: line 11: /usr/bin/readlink: Permission denied"
    with pytest.raises(wgtools_module.WgQuickError) as excinfo:
        _init_server(
            wgtools_module,
            wgtools_hyper,
            iface_present=False,
            up_rc=126,
            up_stderr=stderr,
        )
    message = str(excinfo.value)
    assert "126" in message
    assert "readlink: Permission denied" in message
    assert "AppArmor" in message
    assert excinfo.value.returncode == 126
