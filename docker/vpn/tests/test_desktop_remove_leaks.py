# SPDX-License-Identifier: AGPL-3.0-or-later
"""A desktop whose user row is gone must still have its remotevpn rules reaped."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def uipt(simple_iptools):
    # Skip __init__: it shells out to iptables and hits the database.
    return simple_iptools.UserIpTools.__new__(simple_iptools.UserIpTools)


def _remove(simple_iptools_module, uipt, *, user_row):
    conn = MagicMock()
    conn.__enter__ = MagicMock(return_value=conn)
    conn.__exit__ = MagicMock(return_value=False)
    table = MagicMock()
    table.get.return_value.run.return_value = user_row
    with patch.object(
        simple_iptools_module, "vpn_rethink_conn", return_value=conn
    ), patch.object(simple_iptools_module.r, "table", return_value=table), patch.object(
        simple_iptools_module, "check_output", MagicMock(return_value="")
    ), patch.object(
        uipt, "remove_remote_vpn", MagicMock()
    ) as reap:
        uipt.desktop_remove("u1", "192.0.2.5")
    return reap


def test_a_deleted_user_still_gets_its_desktop_rules_reaped(simple_iptools, uipt):
    reap = _remove(simple_iptools, uipt, user_row=None)
    assert reap.called, "remove_remote_vpn must run even with no user row"
    assert reap.call_args.args[1] == "192.0.2.5"


def test_an_unreadable_user_row_still_gets_its_desktop_rules_reaped(
    simple_iptools, uipt
):
    reap = _remove(simple_iptools, uipt, user_row={"vpn": None})
    assert reap.called, "a malformed user row must not skip the reap"


def test_a_readable_user_is_unchanged(simple_iptools, uipt):
    reap = _remove(
        simple_iptools,
        uipt,
        user_row={"vpn": {"wireguard": {"Address": "192.0.2.9"}}},
    )
    assert reap.called
