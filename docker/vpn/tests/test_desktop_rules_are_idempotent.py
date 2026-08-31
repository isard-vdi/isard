# SPDX-License-Identifier: AGPL-3.0-or-later
"""What the FORWARD chain looks like after a desktop's events replay.

``desktop_iptables`` installs the rules from any update carrying a Started
status and a guest ip, and a running desktop's row is written for all sorts
of reasons. Nothing in the emitted commands tells you what that does to the
chain, so these assert on the chain: they run against a fake netfilter that
keeps the rules, not against a mock that only remembers the calls.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

USER = {"id": "alice", "vpn": {"wireguard": {"Address": "10.0.0.2"}}}
DESKTOP_IP = "10.2.0.77"
OUTBOUND = ("-s", "10.0.0.2", "-d", DESKTOP_IP, "-j", "ACCEPT")
INBOUND = ("-d", "10.0.0.2", "-s", DESKTOP_IP, "-j", "ACCEPT")


class _FakeR:
    """Just enough of the driver for ``r.table("users").get(id).run(conn)``."""

    def __init__(self, user):
        self._user = user

    def table(self, _name):
        return self

    def get(self, _key):
        return self

    def run(self, _conn):
        return self._user


@pytest.fixture
def uipt(simple_iptools, fake_iptables):
    # Skip __init__: it shells out to iptables and reaches the database.
    instance = simple_iptools.UserIpTools.__new__(simple_iptools.UserIpTools)
    with patch.object(simple_iptools, "check_output", fake_iptables), patch.object(
        simple_iptools, "r", _FakeR(USER)
    ), patch.object(instance, "get_extra_alloweds", return_value=[]):
        yield instance


def test_replaying_the_add_leaves_one_pair(uipt, fake_iptables):
    for _ in range(4):
        uipt.desktop_add("alice", DESKTOP_IP)

    assert fake_iptables.count(*OUTBOUND) == 1
    assert fake_iptables.count(*INBOUND) == 1


def test_one_remove_clears_a_desktop_whose_add_was_replayed(uipt, fake_iptables):
    for _ in range(4):
        uipt.desktop_add("alice", DESKTOP_IP)

    uipt.desktop_remove("alice", DESKTOP_IP)

    # A leftover here outlives the desktop, and the guest ip gets reused.
    assert [rule for rule in fake_iptables.forward if DESKTOP_IP in rule] == []


def test_the_remotevpn_pair_is_not_duplicated_either(
    simple_iptools, uipt, fake_iptables
):
    entry = {
        "id": "rvpn",
        "allowed": {"users": ["alice"]},
        "vpn": {"wireguard": {"Address": "10.9.0.5", "extra_client_nets": None}},
    }
    with patch.object(uipt, "get_extra_alloweds", return_value=[entry]):
        for _ in range(3):
            uipt.desktop_add("alice", DESKTOP_IP)

    assert fake_iptables.count("-s", DESKTOP_IP, "-d", "10.9.0.5", "-j", "ACCEPT") == 1
    assert fake_iptables.count("-d", DESKTOP_IP, "-s", "10.9.0.5", "-j", "ACCEPT") == 1
