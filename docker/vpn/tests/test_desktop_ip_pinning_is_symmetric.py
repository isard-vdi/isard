# SPDX-License-Identifier: AGPL-3.0-or-later
"""Whatever ``_remove_table2_flow`` deletes, something must have installed."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

DESKTOP_IP = "192.168.128.5"
DESKTOP_MAC = "52:54:00:11:22:33"
LEASES = (
    f"1790373254 {DESKTOP_MAC} {DESKTOP_IP} * *\n"
    "1790370000 52:54:00:44:55:66 192.168.128.9 other *\n"
)


@pytest.fixture
def wg(wgtools_module):
    Wg = wgtools_module.Wg
    instance = Wg.__new__(Wg)
    instance.table = "users"
    instance.interface = "users"
    instance.uipt = MagicMock()
    return instance


@pytest.fixture
def leases(tmp_path):
    path = tmp_path / "vlan-wg.leases"
    path.write_text(LEASES)
    return path


def _started(guest_ip, domain_id="d1", user="u1"):
    return {
        "old_val": {"id": domain_id, "user": user, "viewer": {}},
        "new_val": {
            "id": domain_id,
            "user": user,
            "status": "Started",
            "viewer": {"guest_ip": guest_ip},
        },
    }


def _commands(subprocess_mock):
    return [call.args[0] for call in subprocess_mock.run.call_args_list]


def test_a_started_desktop_is_pinned_with_the_mac_from_its_lease(
    wg, wgtools_module, leases
):
    with patch.object(
        wgtools_module, "VLAN_WG_LEASES", str(leases), create=True
    ), patch.object(wgtools_module, "subprocess") as sp:
        wg.desktop_iptables(_started(DESKTOP_IP))

    assert [
        "ovs-ofctl",
        "add-flow",
        "ovsbr0",
        f"table=2,priority=100,ip,dl_src={DESKTOP_MAC},"
        f"nw_src={DESKTOP_IP},actions=NORMAL",
    ] in _commands(sp)


def test_the_pin_installed_is_the_one_the_stop_path_deletes(wg, wgtools_module, leases):
    with patch.object(
        wgtools_module, "VLAN_WG_LEASES", str(leases), create=True
    ), patch.object(wgtools_module, "subprocess") as sp:
        wg.desktop_iptables(_started(DESKTOP_IP))
        added = [c for c in _commands(sp) if "add-flow" in c]
        sp.reset_mock()
        wg._remove_table2_flow(DESKTOP_IP)
        deleted = [c for c in _commands(sp) if "del-flows" in c]

    assert added, "the started path installed no pin at all"
    assert deleted
    assert f"nw_src={DESKTOP_IP}" in added[0][3]
    assert f"nw_src={DESKTOP_IP}" in deleted[0][3]


def test_an_ip_with_no_lease_is_not_pinned_with_a_guessed_mac(
    wg, wgtools_module, leases
):
    with patch.object(
        wgtools_module, "VLAN_WG_LEASES", str(leases), create=True
    ), patch.object(wgtools_module, "subprocess") as sp:
        wg.desktop_iptables(_started("192.168.128.200"))

    assert not [c for c in _commands(sp) if "add-flow" in c]


def test_an_unreadable_lease_file_does_not_take_the_handler_down(
    wg, wgtools_module, tmp_path
):
    with patch.object(
        wgtools_module, "VLAN_WG_LEASES", str(tmp_path / "absent"), create=True
    ), patch.object(wgtools_module, "subprocess") as sp:
        wg.desktop_iptables(_started(DESKTOP_IP))

    wg.uipt.desktop_add.assert_called_once_with("u1", DESKTOP_IP)
    assert not [c for c in _commands(sp) if "add-flow" in c]
