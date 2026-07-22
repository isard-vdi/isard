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


def _calls(mock):
    return [tuple(c.args[0]) for c in mock.call_args_list]


@pytest.fixture
def geneve_env(wgadmin_module, monkeypatch):
    monkeypatch.setenv("WG_HYPERS_PORT", "4443")
    monkeypatch.setattr(
        wgadmin_module.socket, "gethostbyname", lambda h: "10.0.0.9", raising=False
    )
    return wgadmin_module


def test_creates_port_and_enables_bfd_when_missing(geneve_env):
    with patch.object(geneve_env, "check_output", return_value="") as co, patch.object(
        geneve_env, "subprocess"
    ) as sp:
        assert geneve_env.ensure_geneve_port("isard-hypervisor", "hyper.local") is True
    cmds = _calls(sp.run)
    assert any("add-port" in c for c in cmds)
    assert any("bfd:enable=true" in c for c in cmds)


def test_enables_bfd_even_when_port_already_exists(geneve_env):
    """The regression: a pre-existing port must still get its BFD session.

    Previously add-port, bfd:enable and the flows all sat behind the
    "port not in ovs-vsctl show" guard, so an existing port was skipped
    entirely and never acquired BFD -> tunnel_status stuck disconnected.
    """
    # `ovs-vsctl show` reports the port, so add-port must be skipped...
    with patch.object(
        geneve_env, "check_output", return_value="Port isard-hypervisor"
    ), patch.object(geneve_env, "subprocess") as sp:
        assert geneve_env.ensure_geneve_port("isard-hypervisor", "hyper.local") is True
    cmds = _calls(sp.run)
    assert not any("add-port" in c for c in cmds), "must not re-add an existing port"
    # ...but BFD and the flows must still be (re)applied.
    assert any(
        "bfd:enable=true" in c for c in cmds
    ), "existing port must still get its BFD session"
    assert any("add-flow" in c for c in cmds), "flows must be re-applied after restart"


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
