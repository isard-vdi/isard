# SPDX-License-Identifier: AGPL-3.0-or-later
"""A deleted domain must not leave its guest rules behind.

`desktop_add` installs an ACCEPT pair binding the owner's wireguard address to
the desktop's guest ip, plus a table-2 source-ip pinning flow. Both are reaped
from a later event that has to name the same ip, and the delete path had two
ways of failing to do it:

* it only removed the OVS flow and never called ``desktop_remove``, so a desktop
  deleted while still started -- which never passes through the "viewer cleared"
  update -- leaked its ACCEPT pair;
* the ip came from ``old_val.viewer``, which a changefeed-squashed delete does
  not carry (the feed coalesces a write and a delete inside 0.5 s and emits the
  state from *before* the write), so nothing was reaped at all.

A leaked pair authorises traffic for an ip the deleted desktop no longer owns,
and guest ips are reused.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def wg(wgtools_module):
    Wg = wgtools_module.Wg
    instance = Wg.__new__(Wg)
    instance.table = "users"
    instance.interface = "users"
    instance.uipt = MagicMock()
    return instance


def _started(domain_id="d1", user="u1", guest_ip="192.168.128.5"):
    """The update that installs the rules: status Started with a guest ip."""
    return {
        "old_val": {"id": domain_id, "user": user, "viewer": {}},
        "new_val": {
            "id": domain_id,
            "user": user,
            "status": "Started",
            "viewer": {"guest_ip": guest_ip},
        },
    }


def _deleted(old_val):
    return {"old_val": old_val, "new_val": None}


def test_delete_while_started_reaps_the_rules_not_only_the_flow(wg, wgtools_module):
    with patch.object(wgtools_module, "subprocess"):
        wg.desktop_iptables(_started())
        wg.uipt.reset_mock()
        wg.desktop_iptables(
            _deleted(
                {"id": "d1", "user": "u1", "viewer": {"guest_ip": "192.168.128.5"}}
            )
        )

    wg.uipt.desktop_remove.assert_called_once_with("u1", "192.168.128.5")


def test_squashed_delete_still_reaps_both(wg, wgtools_module):
    """The measured shape: the delete arrives with the pre-write row, so no
    viewer and no ip."""
    with patch.object(wgtools_module, "subprocess") as sp:
        wg.desktop_iptables(_started())
        wg.uipt.reset_mock()
        sp.reset_mock()
        wg.desktop_iptables(_deleted({"id": "d1"}))

    wg.uipt.desktop_remove.assert_called_once_with("u1", "192.168.128.5")
    flows = [c.args[0] for c in sp.run.call_args_list]
    assert [
        "ovs-ofctl",
        "del-flows",
        "ovsbr0",
        "table=2,ip,nw_src=192.168.128.5",
    ] in flows


@pytest.mark.parametrize(
    "old_val",
    [
        pytest.param({"id": "d1"}, id="no-viewer-at-all"),
        pytest.param({"id": "d1", "viewer": None}, id="viewer-is-null"),
        pytest.param({"id": "d1", "viewer": {}}, id="viewer-is-empty"),
        pytest.param({"id": "d1", "viewer": {"guest_ip": None}}, id="ip-is-null"),
        pytest.param({"id": "d1", "viewer": {"guest_ip": ""}}, id="ip-is-empty"),
    ],
)
def test_every_gutted_delete_shape_falls_back_to_the_index(wg, wgtools_module, old_val):
    with patch.object(wgtools_module, "subprocess"):
        wg.desktop_iptables(_started())
        wg.uipt.reset_mock()
        wg.desktop_iptables(_deleted(old_val))

    wg.uipt.desktop_remove.assert_called_once_with("u1", "192.168.128.5")


def test_the_event_wins_when_it_carries_an_ip(wg, wgtools_module):
    """A stale index entry must never override what the event says."""
    wg._remember_applied_desktop("d1", "u1", "192.168.128.99")
    with patch.object(wgtools_module, "subprocess"):
        wg.desktop_iptables(
            _deleted(
                {"id": "d1", "user": "u1", "viewer": {"guest_ip": "192.168.128.5"}}
            )
        )

    wg.uipt.desktop_remove.assert_called_once_with("u1", "192.168.128.5")


def test_a_domain_that_never_started_is_a_quiet_noop(wg, wgtools_module, caplog):
    """The common case by far. It must not reap anything and must not shout --
    an error per deleted domain only teaches people to ignore the log."""
    with patch.object(wgtools_module, "subprocess") as sp:
        with caplog.at_level("INFO"):
            wg.desktop_iptables(_deleted({"id": "never-started"}))

    wg.uipt.desktop_remove.assert_not_called()
    sp.run.assert_not_called()
    assert caplog.text == ""


def test_a_stopped_desktop_is_reaped_once_not_twice(wg, wgtools_module):
    """Stopping clears the viewer and reaps; the later delete must find nothing
    left, or an ip already reassigned would be reaped out from under its new
    owner."""
    with patch.object(wgtools_module, "subprocess"):
        wg.desktop_iptables(_started())
        wg.desktop_iptables(
            {
                "old_val": {
                    "id": "d1",
                    "user": "u1",
                    "viewer": {"guest_ip": "192.168.128.5"},
                },
                "new_val": {
                    "id": "d1",
                    "user": "u1",
                    "status": "Stopped",
                    "viewer": {},
                },
            }
        )
        wg.uipt.reset_mock()
        wg.desktop_iptables(_deleted({"id": "d1"}))

    wg.uipt.desktop_remove.assert_not_called()


def test_two_desktops_do_not_shadow_each_other(wg, wgtools_module):
    with patch.object(wgtools_module, "subprocess"):
        wg.desktop_iptables(_started("d1", "u1", "192.168.128.5"))
        wg.desktop_iptables(_started("d2", "u2", "192.168.128.6"))
        wg.uipt.reset_mock()
        wg.desktop_iptables(_deleted({"id": "d1"}))

    wg.uipt.desktop_remove.assert_called_once_with("u1", "192.168.128.5")
    assert "d2" in wg._applied_desktops


def test_an_insert_is_still_ignored(wg, wgtools_module):
    """A new domain has no ip yet; nothing to install, nothing to record."""
    with patch.object(wgtools_module, "subprocess"):
        wg.desktop_iptables({"old_val": None, "new_val": {"id": "d9"}})

    assert wg._applied_desktops == {}
    wg.uipt.desktop_add.assert_not_called()


def test_desktop_remove_error_path_does_not_raise_over_the_real_cause(monkeypatch):
    """The handler concatenated the exception itself, which raised a TypeError
    from inside the except block and buried the original error.

    Loaded from its file path, like the other simple_iptools tests: the shared
    fixtures replace the module in ``sys.modules`` with a stub, since the real
    one imports the native ``iptc``.
    """
    import importlib.util
    import sys
    import types
    from pathlib import Path

    src_dir = Path(__file__).resolve().parent.parent / "src"
    db_stub = types.ModuleType("db")
    db_stub.vpn_rethink_conn = lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("db down")
    )
    monkeypatch.setitem(sys.modules, "db", db_stub)
    monkeypatch.syspath_prepend(str(src_dir))
    iptc_stub = types.ModuleType("iptc")
    monkeypatch.setitem(sys.modules, "iptc", iptc_stub)

    spec = importlib.util.spec_from_file_location(
        "simple_iptools_reap_test", str(src_dir / "simple_iptools.py")
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    tools = module.UserIpTools.__new__(module.UserIpTools)
    tools.desktop_remove("u1", "192.168.128.5")  # must not raise
