# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verify the typed-envelope dispatch path in wgadmin.

These tests exercise ``wgadmin._process_vpn_change`` through the same
``TABLE_TO_SUBSCRIBER[...].parse_dict`` hop that ``handle_change`` uses at
runtime, so the typed-envelope migration is covered end-to-end (dict → Pydantic
envelope → dispatch to the right ``Wg`` helper).
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from changefeed_subscribers import TABLE_TO_SUBSCRIBER


@pytest.fixture
def process_change(wgadmin_module):
    return wgadmin_module._process_vpn_change


def test_hypervisor_insert_routes_to_wg_hypers(process_change):
    wg_users = MagicMock()
    wg_hypers = MagicMock()

    raw_msg = {
        "table": "hypervisors",
        "change": {
            "new_val": {
                "id": "h1",
                "table": "hypervisors",
                "hostname": "hyper1",
                "vpn": {
                    "wireguard": {
                        "keys": {"public": "PUB", "private": "PRIV"},
                    },
                },
            },
            "old_val": None,
        },
    }
    envelope = TABLE_TO_SUBSCRIBER["hypervisors"].parse_dict(raw_msg)

    process_change(envelope.change, wg_users, wg_hypers)

    # Default tunneling_mode ("wireguard+geneve") routes through the WireGuard
    # add_peer branch; wg_users must not be touched for hypervisor inserts.
    assert wg_hypers.add_peer.called
    assert not wg_users.add_peer.called
    assert not wg_users.down_peer.called


def test_user_insert_routes_to_wg_users(process_change):
    wg_users = MagicMock()
    wg_hypers = MagicMock()

    raw_msg = {
        "table": "users",
        "change": {
            "new_val": {
                "id": "u1",
                "table": "users",
                "username": "alice",
                "category": "default",
                "group": "default",
                "name": "Alice",
                "role": "user",
                "active": True,
            },
            "old_val": None,
        },
    }
    envelope = TABLE_TO_SUBSCRIBER["users"].parse_dict(raw_msg)

    process_change(envelope.change, wg_users, wg_hypers)

    wg_users.add_peer.assert_called_once()
    # The hypervisor helper must not be invoked on a users event.
    assert not wg_hypers.add_peer.called


def test_user_delete_routes_to_wg_users(process_change):
    wg_users = MagicMock()
    wg_hypers = MagicMock()

    raw_msg = {
        "table": "users",
        "change": {
            "new_val": None,
            "old_val": {
                "id": "u1",
                "table": "users",
                "username": "alice",
                "category": "default",
                "group": "default",
                "name": "Alice",
                "role": "user",
                "active": True,
            },
        },
    }
    envelope = TABLE_TO_SUBSCRIBER["users"].parse_dict(raw_msg)

    process_change(envelope.change, wg_users, wg_hypers)

    wg_users.down_peer.assert_called_once()
    assert not wg_hypers.down_peer.called


def test_process_vpn_change_update_with_explicit_null_vpn(process_change):
    """Regression: an update where old_val has an explicit ``vpn: None``
    must still be processed. Original behaviour used ``"vpn" not in ...``
    which treats a null-key as present and continues to the reset-keys
    branch when new_val.vpn.wireguard.keys is False."""
    wg_users = MagicMock()
    wg_hypers = MagicMock()

    raw_msg = {
        "table": "users",
        "change": {
            "old_val": {
                "id": "u-1",
                "table": "users",
                "username": "alice",
                "category": "default",
                "group": "default",
                "name": "Alice",
                "role": "user",
                "active": True,
                "vpn": None,
            },
            "new_val": {
                "id": "u-1",
                "table": "users",
                "username": "alice",
                "category": "default",
                "group": "default",
                "name": "Alice",
                "role": "user",
                "active": True,
                "vpn": {"wireguard": {"keys": False}},
            },
        },
    }
    envelope = TABLE_TO_SUBSCRIBER["users"].parse_dict(raw_msg)

    process_change(envelope.change, wg_users, wg_hypers)

    assert wg_users.add_peer.called
    assert wg_users.set_user_rules.called


def test_hypervisor_delete_without_wg_hypers_uses_ovs(
    process_change, wgadmin_module, monkeypatch
):
    """When wg_hypers is None (GENEVE_ONLY_INFRA), a hypervisor delete must
    shell out to ovs-ofctl/ovs-vsctl instead of calling a WireGuard helper."""
    captured: list[list[str]] = []

    def _fake_run(cmd, *args, **kwargs):
        captured.append(list(cmd))
        return MagicMock(returncode=0)

    monkeypatch.setattr(wgadmin_module.subprocess, "run", _fake_run)

    wg_users = MagicMock()

    raw_msg = {
        "table": "hypervisors",
        "change": {
            "new_val": None,
            "old_val": {
                "id": "h-gone",
                "table": "hypervisors",
                "hostname": "hyper-dead",
            },
        },
    }
    envelope = TABLE_TO_SUBSCRIBER["hypervisors"].parse_dict(raw_msg)

    process_change(envelope.change, wg_users, None)

    invoked = [cmd[0] for cmd in captured]
    assert "ovs-ofctl" in invoked
    assert "ovs-vsctl" in invoked
    # wg_users must not have been touched — this is a hypervisor-only path.
    assert not wg_users.down_peer.called
