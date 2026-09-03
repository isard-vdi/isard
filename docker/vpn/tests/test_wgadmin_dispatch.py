# SPDX-License-Identifier: AGPL-3.0-or-later
"""Verify the typed-envelope dispatch path in wgadmin.

These tests exercise ``wgadmin._process_vpn_change`` through the same
``TABLE_TO_SUBSCRIBER[...].parse_dict`` hop that ``handle_change`` uses at
runtime, so the typed-envelope migration is covered end-to-end (dict → Pydantic
envelope → dispatch to the right ``Wg`` helper).
"""
from __future__ import annotations

from unittest.mock import MagicMock, create_autospec

import pytest
from changefeed_subscribers import TABLE_TO_SUBSCRIBER


@pytest.fixture
def process_change(wgadmin_module):
    return wgadmin_module._process_vpn_change


@pytest.fixture
def wg_spec(wgtools_module):
    """Build a ``Wg`` stand-in that only answers to what ``Wg`` really has.

    A bare MagicMock invents whatever attribute it is asked for, so a call
    addressed to the wrong receiver passes a dispatch test and fails in
    production. This raises AttributeError instead.
    """
    return lambda: create_autospec(wgtools_module.Wg, instance=True)


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


def test_remotevpn_allowed_change_reaches_the_wg_helper(process_change, wg_spec):
    wg_users = wg_spec()
    wg_hypers = MagicMock()

    base = {
        "id": "rvpn-1",
        "table": "remotevpn",
        "vpn": {"wireguard": {"Address": "10.0.0.3"}},
    }
    raw_msg = {
        "table": "remotevpn",
        "change": {
            "old_val": {**base, "allowed": {"users": ["u1"]}},
            "new_val": {**base, "allowed": {"users": ["u2"]}},
        },
    }
    envelope = TABLE_TO_SUBSCRIBER["remotevpn"].parse_dict(raw_msg)

    process_change(envelope.change, wg_users, wg_hypers)

    wg_users.refresh_remotevpn_allowed.assert_called_once()
    called_with = wg_users.refresh_remotevpn_allowed.call_args[0][0]
    assert called_with["allowed"] == {"users": ["u2"]}


def test_remotevpn_update_without_an_allowed_change_does_not_refresh(
    process_change, wg_spec
):
    wg_users = wg_spec()

    base = {
        "id": "rvpn-1",
        "table": "remotevpn",
        "allowed": {"users": ["u1"]},
        "vpn": {"wireguard": {"Address": "10.0.0.3"}},
    }
    raw_msg = {
        "table": "remotevpn",
        "change": {
            "old_val": {**base, "description": "before"},
            "new_val": {**base, "description": "after"},
        },
    }
    envelope = TABLE_TO_SUBSCRIBER["remotevpn"].parse_dict(raw_msg)

    process_change(envelope.change, wg_users, MagicMock())

    assert not wg_users.refresh_remotevpn_allowed.called


class TestFailureLoggingNamesTheChange:
    """``_process_vpn_change`` swallows exceptions so one bad change cannot
    stop the ones behind it. That is only tolerable if the log says WHICH
    change was lost -- otherwise a peer silently never gets set up or torn
    down and there is nothing to grep for.
    """

    def _delete_envelope(self, table="users", peer_id="u1"):
        raw_msg = {
            "table": table,
            "change": {"old_val": {"id": peer_id, "table": table}, "new_val": None},
        }
        return TABLE_TO_SUBSCRIBER[table].parse_dict(raw_msg).change

    def test_delete_failure_names_table_id_and_kind(self, process_change, caplog):
        wg_users = MagicMock()
        wg_users.down_peer.side_effect = RuntimeError("boom")

        with caplog.at_level("ERROR"):
            process_change(self._delete_envelope(peer_id="u-42"), wg_users, MagicMock())

        assert "u-42" in caplog.text
        assert "users" in caplog.text
        assert "delete" in caplog.text
        assert "boom" in caplog.text  # the traceback is still there

    def test_insert_failure_is_labelled_insert(self, process_change, caplog):
        raw_msg = {
            "table": "users",
            "change": {
                "old_val": None,
                "new_val": {"id": "u-new", "table": "users"},
            },
        }
        change = TABLE_TO_SUBSCRIBER["users"].parse_dict(raw_msg).change
        wg_users = MagicMock()
        wg_users.add_peer.side_effect = RuntimeError("boom")

        with caplog.at_level("ERROR"):
            process_change(change, wg_users, MagicMock())

        assert "insert" in caplog.text
        assert "u-new" in caplog.text

    def test_a_failure_before_the_values_are_parsed_does_not_raise(
        self, process_change, caplog
    ):
        """The old handler read old_val/new_val in its own except block; if the
        failure happened while building them, that raised NameError and buried
        the real cause."""
        exploding_change = MagicMock()
        type(exploding_change).new_val = property(
            lambda self: (_ for _ in ()).throw(RuntimeError("model_dump exploded"))
        )

        with caplog.at_level("ERROR"):
            process_change(exploding_change, MagicMock(), MagicMock())  # must not raise

        assert "unparsed" in caplog.text
        assert "model_dump exploded" in caplog.text
        assert "NameError" not in caplog.text

    def test_a_change_that_succeeds_logs_no_error(self, process_change, caplog):
        wg_users = MagicMock()
        with caplog.at_level("ERROR"):
            process_change(self._delete_envelope(), wg_users, MagicMock())

        wg_users.down_peer.assert_called_once()
        assert caplog.text == ""
