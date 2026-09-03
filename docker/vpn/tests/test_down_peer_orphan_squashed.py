# SPDX-License-Identifier: AGPL-3.0-or-later
"""An orphan WireGuard peer must not survive a squashed delete event.

Root cause: the changefeed squashes changes to the same document inside a
0.5 s window, so a config-write followed by a delete is emitted as ONE event
whose ``old_val`` is the state *before* the write. ``down_peer`` then receives
a row with no vpn subtree -- neither key nor Address -- and used to skip its
removal block entirely, leaving the peer on the ``users`` interface,
handshaking via persistent-keepalive and 404ing on every reconnect until the
container restarted.

Nothing can be recovered from that event, so removal must not depend on it.
The one identifier a squashed event always carries is the row ``id``, and this
service is the only writer of its interface: it records what it applied, keyed
by id, and resolves the removal from its own record.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def wgtools_users(wgtools_module):
    """A ``Wg`` on the ``users`` interface with no ``__init__`` side effects."""
    Wg = wgtools_module.Wg
    instance = Wg.__new__(Wg)
    instance.table = "users"
    instance.interface = "users"
    instance.uipt = MagicMock()
    return instance


def _user_row(peer_id, address, public, extra_client_nets=None):
    return {
        "id": peer_id,
        "active": True,
        "vpn": {
            "wireguard": {
                "Address": address,
                "keys": {"public": public, "private": "x"},
                "extra_client_nets": extra_client_nets,
            }
        },
    }


def _wg_commands(mock_check_output):
    return [tuple(call.args[0]) for call in mock_check_output.call_args_list]


def test_squashed_delete_still_removes_the_peer(wgtools_users, wgtools_module):
    """The regression: up the peer, then delete it with a gutted ``old_val``.

    This is the exact event shape measured on a live stack for a user created
    and deleted through the API inside the squash window.
    """
    row = _user_row("user-x", "10.1.0.2", "USERXPUB")
    with patch.object(wgtools_module, "subprocess") as mock_sp:
        mock_sp.run.return_value = MagicMock(returncode=0)
        assert wgtools_users.up_peer(row) is True

    squashed_delete = {"id": "user-x", "vpn": None}
    with patch.object(wgtools_module, "check_output", return_value="") as mock_co:
        wgtools_users.down_peer(squashed_delete)

    assert (
        "/usr/bin/wg",
        "set",
        "users",
        "peer",
        "USERXPUB",
        "remove",
    ) in _wg_commands(mock_co)


def test_squashed_delete_also_reaps_the_iptables_rules(wgtools_users, wgtools_module):
    """The peer's ACCEPT pairs are reaped by Address, which the squashed event
    does not carry either -- the reaper must get it from the same record."""
    row = _user_row("user-y", "10.1.0.7", "USERYPUB")
    with patch.object(wgtools_module, "subprocess") as mock_sp:
        mock_sp.run.return_value = MagicMock(returncode=0)
        wgtools_users.up_peer(row)

    with patch.object(wgtools_module, "check_output", return_value=""):
        wgtools_users.down_peer({"id": "user-y", "vpn": None})

    reaped = wgtools_users.uipt.remove_matching_rules.call_args.args[0]
    assert reaped["vpn"]["wireguard"]["Address"] == "10.1.0.7"


def test_event_subtree_wins_over_the_remembered_one(wgtools_users, wgtools_module):
    """A key rotation writes the new key into the event; the event is fresher
    than our record, so it must be the one honoured."""
    wgtools_users._remember_applied_peer(
        "user-z", {"keys": {"public": "OLDPUB"}, "Address": "10.1.0.4"}
    )
    row = _user_row("user-z", "10.1.0.4", "NEWPUB")

    with patch.object(wgtools_module, "check_output", return_value="") as mock_co:
        wgtools_users.down_peer(row)

    cmds = _wg_commands(mock_co)
    assert ("/usr/bin/wg", "set", "users", "peer", "NEWPUB", "remove") in cmds
    assert not any("OLDPUB" in cmd for cmd in cmds)


def test_extra_client_nets_route_is_removed_from_the_record(
    wgtools_users, wgtools_module
):
    row = _user_row(
        "user-n", "10.1.0.5", "USERNPUB", extra_client_nets="192.168.9.0/24"
    )
    with patch.object(wgtools_module, "subprocess") as mock_sp:
        mock_sp.run.return_value = MagicMock(returncode=0)
        wgtools_users.up_peer(row)

    with patch.object(wgtools_module, "check_output", return_value=""), patch.object(
        wgtools_module, "subprocess"
    ) as mock_sp:
        wgtools_users.down_peer({"id": "user-n", "vpn": None})

    routes = [call.args[0] for call in mock_sp.run.call_args_list]
    assert ["ip", "route", "del", "192.168.9.0/24", "dev", "users"] in routes


def test_removal_forgets_the_peer_so_it_is_not_removed_twice(
    wgtools_users, wgtools_module
):
    """A second delete for the same id must not re-issue a removal for a key
    that is no longer ours -- the id could have been recreated since."""
    row = _user_row("user-d", "10.1.0.6", "USERDPUB")
    with patch.object(wgtools_module, "subprocess") as mock_sp:
        mock_sp.run.return_value = MagicMock(returncode=0)
        wgtools_users.up_peer(row)

    with patch.object(wgtools_module, "check_output", return_value=""):
        wgtools_users.down_peer({"id": "user-d", "vpn": None})
    with patch.object(wgtools_module, "check_output", return_value="") as mock_co:
        wgtools_users.down_peer({"id": "user-d", "vpn": None})

    assert not any("USERDPUB" in cmd for cmd in _wg_commands(mock_co))


def test_unresolvable_peer_is_logged_not_silently_skipped(
    wgtools_users, wgtools_module, caplog
):
    """An id we never applied cannot be removed -- that is legitimate, but it
    is exactly the silence the bug hid behind, so it must be logged."""
    with patch.object(wgtools_module, "check_output", return_value="") as mock_co:
        with caplog.at_level("ERROR"):
            wgtools_users.down_peer({"id": "never-seen", "vpn": None})

    assert not any("remove" in cmd for cmd in _wg_commands(mock_co))
    assert "never-seen" in caplog.text


def test_each_interface_keeps_its_own_index(wgtools_module):
    """The users and hypers instances must not share one index."""
    Wg = wgtools_module.Wg
    users = Wg.__new__(Wg)
    users.table = users.interface = "users"
    hypers = Wg.__new__(Wg)
    hypers.table = hypers.interface = "hypervisors"

    users._remember_applied_peer("shared-id", {"keys": {"public": "UPUB"}})

    assert hypers._applied_peers == {}


# --------------------------------------------------------------------------- #
# Every shape an unusable event can take
#
# The squashed delete (vpn=None) is the measured shape, but a reset in flight,
# a half-written subtree and a partially-plucked row all reach down_peer with
# something that looks like a config and is not one.
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "unusable_vpn",
    [
        pytest.param(None, id="squashed-subtree-is-null"),
        pytest.param({}, id="vpn-present-but-empty"),
        pytest.param({"wireguard": None}, id="wireguard-is-null"),
        pytest.param({"wireguard": {}}, id="wireguard-present-but-empty"),
        pytest.param({"wireguard": {"Address": "10.1.0.2"}}, id="no-keys-at-all"),
        pytest.param(
            {"wireguard": {"Address": "10.1.0.2", "keys": False}},
            id="keys-false-reset-in-flight",
        ),
        pytest.param(
            {"wireguard": {"Address": "10.1.0.2", "keys": {}}},
            id="keys-empty-dict",
        ),
        pytest.param(
            {"wireguard": {"Address": "10.1.0.2", "keys": {"public": None}}},
            id="public-key-is-null",
        ),
        pytest.param(
            {"wireguard": {"Address": "10.1.0.2", "keys": {"public": ""}}},
            id="public-key-is-empty",
        ),
    ],
)
def test_any_unusable_event_falls_back_to_the_index(
    wgtools_users, wgtools_module, unusable_vpn
):
    row = _user_row("user-p", "10.1.0.2", "USERPPUB")
    with patch.object(wgtools_module, "subprocess") as mock_sp:
        mock_sp.run.return_value = MagicMock(returncode=0)
        wgtools_users.up_peer(row)

    with patch.object(wgtools_module, "check_output", return_value="") as mock_co:
        wgtools_users.down_peer({"id": "user-p", "vpn": unusable_vpn})

    assert (
        "/usr/bin/wg",
        "set",
        "users",
        "peer",
        "USERPPUB",
        "remove",
    ) in _wg_commands(mock_co)


def test_a_peer_that_never_went_up_is_never_remembered(wgtools_users, wgtools_module):
    """``up_peer`` refuses a row whose keys are not ready. Remembering it would
    invent a peer that is not on the interface."""
    not_ready = _user_row("user-nr", "10.1.0.8", "IGNORED")
    not_ready["vpn"]["wireguard"]["keys"] = False

    with patch.object(wgtools_module, "subprocess") as mock_sp:
        mock_sp.run.return_value = MagicMock(returncode=0)
        assert wgtools_users.up_peer(not_ready) is False

    assert "user-nr" not in wgtools_users._applied_peers


@pytest.mark.parametrize(
    "peer_id,wireguard",
    [
        pytest.param(None, {"keys": {"public": "P"}}, id="no-id"),
        pytest.param("", {"keys": {"public": "P"}}, id="empty-id"),
        pytest.param("x", None, id="wireguard-is-null"),
        pytest.param("x", {}, id="wireguard-empty"),
        pytest.param("x", {"keys": False}, id="keys-false"),
        pytest.param("x", {"keys": {}}, id="keys-without-public"),
    ],
)
def test_remembering_junk_is_a_noop_not_a_crash(wgtools_users, peer_id, wireguard):
    wgtools_users._remember_applied_peer(peer_id, wireguard)
    assert wgtools_users._applied_peers == {}


def test_a_rotation_replaces_the_remembered_key(wgtools_users, wgtools_module):
    """reset_vpn tears the peer down and brings it back with new keys. The
    index must hold one entry per row, the current one."""
    with patch.object(wgtools_module, "subprocess") as mock_sp:
        mock_sp.run.return_value = MagicMock(returncode=0)
        wgtools_users.up_peer(_user_row("user-r", "10.1.0.3", "FIRSTPUB"))
        wgtools_users.up_peer(_user_row("user-r", "10.1.0.3", "SECONDPUB"))

    assert wgtools_users._applied_peers["user-r"]["public"] == "SECONDPUB"

    with patch.object(wgtools_module, "check_output", return_value="") as mock_co:
        wgtools_users.down_peer({"id": "user-r", "vpn": None})

    cmds = _wg_commands(mock_co)
    assert ("/usr/bin/wg", "set", "users", "peer", "SECONDPUB", "remove") in cmds
    assert not any("FIRSTPUB" in cmd for cmd in cmds)


def test_two_rows_do_not_shadow_each_other(wgtools_users, wgtools_module):
    with patch.object(wgtools_module, "subprocess") as mock_sp:
        mock_sp.run.return_value = MagicMock(returncode=0)
        wgtools_users.up_peer(_user_row("user-a", "10.1.0.10", "APUB"))
        wgtools_users.up_peer(_user_row("user-b", "10.1.0.11", "BPUB"))

    with patch.object(wgtools_module, "check_output", return_value="") as mock_co:
        wgtools_users.down_peer({"id": "user-a", "vpn": None})

    cmds = _wg_commands(mock_co)
    assert ("/usr/bin/wg", "set", "users", "peer", "APUB", "remove") in cmds
    assert not any("BPUB" in cmd for cmd in cmds)
    assert "user-b" in wgtools_users._applied_peers


def test_a_geneve_only_hypervisor_delete_is_not_an_error(wgtools_module, caplog):
    """A geneve-only hypervisor legitimately has no wireguard peer. Its delete
    must still tear the OVS port down, and must NOT be reported as an
    unresolvable peer -- that log line has to stay meaningful."""
    Wg = wgtools_module.Wg
    hypers = Wg.__new__(Wg)
    hypers.table = hypers.interface = "hypervisors"
    hypers.uipt = MagicMock()

    with patch.object(wgtools_module, "check_output", return_value="3") as mock_co:
        with patch.object(wgtools_module, "subprocess") as mock_sp:
            mock_sp.run.return_value = MagicMock(returncode=0)
            mock_sp.CalledProcessError = Exception
            with caplog.at_level("ERROR"):
                hypers.down_peer({"id": "hyp-geneve", "vpn": None})

    assert "cannot resolve a public key" not in caplog.text
    assert any("del-port" in cmd for cmd in _wg_commands(mock_co))


def test_the_index_is_not_shared_between_two_users_instances(wgtools_module):
    """Two Wg objects on the same table are still distinct services; a class
    attribute would have made one see the other's peers."""
    Wg = wgtools_module.Wg
    first = Wg.__new__(Wg)
    first.table = first.interface = "users"
    second = Wg.__new__(Wg)
    second.table = second.interface = "users"

    first._remember_applied_peer("u1", {"keys": {"public": "P1"}})

    assert second._applied_peers == {}
    assert first._applied_peers["u1"]["public"] == "P1"


def test_forgetting_an_unknown_id_is_a_noop(wgtools_users):
    wgtools_users._forget_applied_peer("never-there")
    wgtools_users._forget_applied_peer(None)
    assert wgtools_users._applied_peers == {}


def test_the_reaper_gets_the_event_subtree_untouched_when_it_is_usable(
    wgtools_users, wgtools_module
):
    """Backfilling is only for the gutted case; a complete event must reach the
    iptables reaper exactly as it arrived."""
    row = _user_row("user-c", "10.1.0.12", "USERCPUB")
    with patch.object(wgtools_module, "check_output", return_value=""):
        wgtools_users.down_peer(row)

    assert wgtools_users.uipt.remove_matching_rules.call_args.args[0] is row
