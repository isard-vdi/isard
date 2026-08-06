# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for ``simple_iptools.UserIpTools.remove_matching_rules``.

The reaper now enumerates the FORWARD chain via the iptables binary
(``iptables -S FORWARD``) instead of python-iptables, and matches peer IPs
**exactly**. These tests pin that behaviour: only the peer's ACCEPT pairs are
deleted, the REJECT/policy rules and unrelated peers are never touched, and
extra-net rules are reaped in both directions.
"""
from __future__ import annotations

from unittest.mock import patch

from isardvdi_vpn import simple_iptools


def _uipt(module):
    # Skip __init__ (flush_chains/set_default_policy/init_domains_started all
    # shell out to iptables and hit the DB).
    return module.UserIpTools.__new__(module.UserIpTools)


# A representative FORWARD dump as printed by `iptables -S FORWARD`.
FORWARD_DUMP = "\n".join(
    [
        "-P FORWARD DROP",
        "-A FORWARD -i users -o users -j REJECT --reject-with icmp-host-prohibited",
        "-A FORWARD -i users -d 10.2.0.0/28 -j REJECT --reject-with icmp-host-prohibited",
        "-A FORWARD -s 10.0.0.5/32 -d 10.2.1.3/32 -j ACCEPT",
        "-A FORWARD -d 10.0.0.5/32 -s 10.2.1.3/32 -j ACCEPT",
        # Unrelated peer whose address is a substring of 10.0.0.5 -> must NOT match.
        "-A FORWARD -s 10.0.0.50/32 -d 10.2.7.1/32 -j ACCEPT",
    ]
)


def _run(module, peer, dump):
    deletes = []

    def fake_check_output(args, **kwargs):
        if args[1] == "-S":
            return dump
        deletes.append(list(args))
        return ""

    with patch.object(module, "check_output", side_effect=fake_check_output):
        _uipt(module).remove_matching_rules(peer)
    return deletes


def test_removes_only_matching_accept_pairs():
    peer = {"vpn": {"wireguard": {"Address": "10.0.0.5", "extra_client_nets": None}}}
    deletes = _run(simple_iptools, peer, FORWARD_DUMP)

    assert len(deletes) == 2  # both directions for 10.0.0.5
    assert all(d[1] == "-D" and d[2] == "FORWARD" for d in deletes)
    assert all("ACCEPT" in d for d in deletes)
    assert all("REJECT" not in d for d in deletes)  # isolation rules untouched
    # Exact match: the unrelated 10.0.0.50 peer is never deleted (no substring hit).
    assert all("10.0.0.50/32" not in d for d in deletes)
    # The deletes reproduce the exact rule specs (append -> delete).
    assert [
        "/sbin/iptables",
        "-D",
        "FORWARD",
        "-s",
        "10.0.0.5/32",
        "-d",
        "10.2.1.3/32",
        "-j",
        "ACCEPT",
    ] in deletes
    assert [
        "/sbin/iptables",
        "-D",
        "FORWARD",
        "-d",
        "10.0.0.5/32",
        "-s",
        "10.2.1.3/32",
        "-j",
        "ACCEPT",
    ] in deletes


def test_no_address_is_noop():
    with patch.object(simple_iptools, "check_output") as m:
        _uipt(simple_iptools).remove_matching_rules({"vpn": {"wireguard": {}}})
    m.assert_not_called()


def test_none_peer_is_noop():
    with patch.object(simple_iptools, "check_output") as m:
        _uipt(simple_iptools).remove_matching_rules(None)
    m.assert_not_called()


def test_extra_client_nets_matched_both_directions():
    peer = {
        "vpn": {
            "wireguard": {"Address": "10.0.0.5", "extra_client_nets": "10.50.0.0/24"}
        }
    }
    dump = "\n".join(
        [
            "-A FORWARD -s 10.2.1.3/32 -d 10.50.0.0/24 -j ACCEPT",
            "-A FORWARD -d 10.2.1.3/32 -s 10.50.0.0/24 -j ACCEPT",
        ]
    )
    deletes = _run(simple_iptools, peer, dump)
    # Both directions of the extra-net rule are reaped (the old substring code
    # matched the dst-side only).
    assert len(deletes) == 2
    assert all("10.50.0.0/24" in d for d in deletes)
