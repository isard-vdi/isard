# SPDX-License-Identifier: AGPL-3.0-or-later
"""A delete that lands while the init_peers queue drains must win.

``init_peers`` hands the ``up_peer`` work to a background thread, so for as
long as that queue is draining the changefeed is already live. A peer deleted
in that window is taken down first and then brought straight back up by its
own queued entry, with nothing left to remove it.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch


def _wg(wgtools_module):
    Wg = wgtools_module.Wg
    instance = Wg.__new__(Wg)
    instance.table = "users"
    instance.interface = "wg0"
    instance.uipt = MagicMock()
    return instance


def test_a_peer_taken_down_mid_drain_is_not_brought_up(wgtools_module):
    wg = _wg(wgtools_module)
    wg._torn_down_while_draining = {"user-2"}
    peers = [{"id": "user-1"}, {"id": "user-2"}, {"id": "user-3"}]

    with patch.object(wg, "up_peer") as up, patch.object(
        wg, "_to_model", side_effect=lambda p: p
    ):
        wg._drain_up_peer_queue("users", peers)

    assert [c.args[0]["id"] for c in up.call_args_list] == ["user-1", "user-3"]


def test_down_peer_records_the_teardown_while_a_drain_is_pending(wgtools_module):
    wg = _wg(wgtools_module)
    wg._torn_down_while_draining = set()

    with patch.object(wgtools_module, "check_output", return_value=""), patch.object(
        wgtools_module.subprocess,
        "run",
        return_value=MagicMock(returncode=0, stderr=""),
    ):
        wg.down_peer({"id": "user-2", "vpn": None}, table="users")

    assert "user-2" in wg._torn_down_while_draining


def test_a_teardown_outside_a_drain_records_nothing(wgtools_module):
    wg = _wg(wgtools_module)

    with patch.object(wgtools_module, "check_output", return_value=""), patch.object(
        wgtools_module.subprocess,
        "run",
        return_value=MagicMock(returncode=0, stderr=""),
    ):
        wg.down_peer({"id": "user-2", "vpn": None}, table="users")

    assert getattr(wg, "_torn_down_while_draining", None) is None
