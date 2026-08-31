# SPDX-License-Identifier: AGPL-3.0-or-later
"""Unit tests for remotevpn permission changes reaching a running desktop.

Permissions used to be read only when a desktop started, and the teardown path
read them again at stop time. A permission withdrawn in between was therefore
invisible twice over: nothing re-evaluated the running desktop, and the stop
looked up the *current* permissions to decide what to delete, so the rule of an
entry the user could no longer reach was never removed.

These pin the three halves of the fix: teardown works from every entry, the
group check honours secondary groups, and a change to ``allowed`` re-applies
the entry across the desktops that are up.
"""
from __future__ import annotations

import importlib.util
import sys
import types
from pathlib import Path
from subprocess import CalledProcessError
from unittest.mock import MagicMock, patch

import pytest

SRC_DIR = Path(__file__).resolve().parent.parent / "src"

ALLOWED_NONE = {"roles": False, "categories": False, "groups": False, "users": False}


def _entry(entry_id, address, allowed, extra_nets=None):
    return {
        "id": entry_id,
        "allowed": dict(ALLOWED_NONE, **allowed),
        "vpn": {
            "wireguard": {"Address": address, "extra_client_nets": extra_nets},
        },
    }


def _iptables_mock():
    """A check_output stand-in that reports every rule as absent.

    The append path asks ``iptables -C`` first once it is idempotent, and a bare
    mock answers that successfully — so the guard concludes the rule is already
    there and never appends. Raising for ``-C`` keeps these asserting on the
    adds and removes they are about.
    """
    mock = MagicMock()

    def _run(argv, *args, **kwargs):
        if "-C" in argv:
            raise CalledProcessError(1, argv)
        return b""

    mock.side_effect = _run
    return mock


@pytest.fixture()
def simple_iptools(monkeypatch):
    db_stub = types.ModuleType("db")

    class _FakeVpnRethinkConn:
        def __enter__(self):
            return object()

        def __exit__(self, *args):
            return False

    db_stub.vpn_rethink_conn = _FakeVpnRethinkConn  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "db", db_stub)
    monkeypatch.syspath_prepend(str(SRC_DIR))

    spec = importlib.util.spec_from_file_location(
        "simple_iptools_remotevpn_under_test", str(SRC_DIR / "simple_iptools.py")
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _uipt(module):
    # Skip __init__: it shells out to iptables and reaches the database.
    return module.UserIpTools.__new__(module.UserIpTools)


def _rules(calls, op):
    """The (source, destination) of every iptables call with this operation."""
    out = []
    for call in calls:
        argv = call.args[0]
        if op in argv:
            out.append((argv[argv.index("-s") + 1], argv[argv.index("-d") + 1]))
    return out


def _peers(calls, op, desktop_ip):
    """The remote address of each rule: whichever end is not the desktop."""
    return [src if dst == desktop_ip else dst for src, dst in _rules(calls, op)]


class TestTeardownCoversRevokedEntries:
    def test_removes_rules_of_an_entry_the_user_may_no_longer_reach(
        self, simple_iptools
    ):
        uipt = _uipt(simple_iptools)
        revoked = _entry("gone", "10.9.0.5/32", {"users": ["someone-else"]})
        still_ok = _entry("open", "10.9.0.6/32", {"users": []})
        user = {"id": "alice", "role": "user", "category": "cat", "group": "grp"}

        with patch.object(
            uipt, "get_all_remotevpn", return_value=[revoked, still_ok]
        ), patch.object(simple_iptools, "check_output", _iptables_mock()) as run:
            uipt.remove_remote_vpn(user, "192.168.1.10")

        # The revoked entry is exactly the one the old teardown skipped.
        deleted = _peers(run.mock_calls, "-D", "192.168.1.10")
        assert "10.9.0.5/32" in deleted
        assert "10.9.0.6/32" in deleted

    def test_a_failing_delete_does_not_stop_the_rest(self, simple_iptools):
        uipt = _uipt(simple_iptools)
        entries = [
            _entry("a", "10.9.0.5/32", {"users": []}),
            _entry("b", "10.9.0.6/32", {"users": []}),
        ]

        with patch.object(
            uipt, "get_all_remotevpn", return_value=entries
        ), patch.object(
            simple_iptools, "check_output", side_effect=Exception("no such rule")
        ):
            uipt.remove_remote_vpn({"id": "alice"}, "192.168.1.10")

    def test_extra_client_nets_are_torn_down_too(self, simple_iptools):
        uipt = _uipt(simple_iptools)
        entry = _entry("a", "10.9.0.5/32", {"users": []}, extra_nets="10.9.1.0/24")

        with patch.object(
            uipt, "get_all_remotevpn", return_value=[entry]
        ), patch.object(simple_iptools, "check_output", _iptables_mock()) as run:
            uipt.remove_remote_vpn({"id": "alice"}, "192.168.1.10")

        assert set(_peers(run.mock_calls, "-D", "192.168.1.10")) == {
            "10.9.0.5/32",
            "10.9.1.0/24",
        }

    def test_an_entry_without_an_address_is_skipped(self, simple_iptools):
        uipt = _uipt(simple_iptools)
        assert uipt._remotevpn_addrs({"vpn": {"wireguard": {}}}) == []
        assert uipt._remotevpn_addrs({}) == []


class TestIsAllowedRemotevpn:
    USER = {
        "id": "alice",
        "role": "advanced",
        "category": "cat",
        "group": "grp-a",
        "secondary_groups": ["grp-b"],
    }

    def test_secondary_group_grants_access(self, simple_iptools):
        entry = _entry("a", "10.9.0.5/32", {"groups": ["grp-b"]})
        assert simple_iptools.UserIpTools.is_allowed_remotevpn(self.USER, entry) is True

    def test_unrelated_group_does_not(self, simple_iptools):
        entry = _entry("a", "10.9.0.5/32", {"groups": ["grp-z"]})
        assert (
            simple_iptools.UserIpTools.is_allowed_remotevpn(self.USER, entry) is False
        )

    def test_empty_list_means_everybody(self, simple_iptools):
        entry = _entry("a", "10.9.0.5/32", {"roles": []})
        assert simple_iptools.UserIpTools.is_allowed_remotevpn(self.USER, entry) is True

    def test_false_means_do_not_check_that_level(self, simple_iptools):
        entry = _entry("a", "10.9.0.5/32", {"users": ["alice"]})
        assert simple_iptools.UserIpTools.is_allowed_remotevpn(self.USER, entry) is True

    def test_no_level_matching_is_refused(self, simple_iptools):
        entry = _entry("a", "10.9.0.5/32", {"users": ["bob"]})
        assert (
            simple_iptools.UserIpTools.is_allowed_remotevpn(self.USER, entry) is False
        )

    def test_a_user_with_no_secondary_groups_is_fine(self, simple_iptools):
        user = {"id": "bob", "role": "user", "category": "cat", "group": "grp-a"}
        entry = _entry("a", "10.9.0.5/32", {"groups": ["grp-a"]})
        assert simple_iptools.UserIpTools.is_allowed_remotevpn(user, entry) is True


class TestRefreshRemotevpnAllowed:
    """The path that did not exist: reacting to ``allowed`` while a desktop runs."""

    def _patch_db(self, module, monkeypatch, desktops, users):
        def table(name):
            class _Q:
                def get_all(self, *a, **k):
                    return self

                def pluck(self, *a, **k):
                    return self

                def get(self, key):
                    self._key = key
                    return self

                def run(self, conn):
                    if name == "domains":
                        return list(desktops)
                    return users.get(self._key)

            return _Q()

        monkeypatch.setattr(module.r, "table", table)

    def test_revoked_user_loses_the_rule_and_allowed_user_keeps_it(
        self, simple_iptools, monkeypatch
    ):
        uipt = _uipt(simple_iptools)
        desktops = [
            {"id": "d1", "user": "alice", "viewer": {"guest_ip": "192.168.1.10"}},
            {"id": "d2", "user": "bob", "viewer": {"guest_ip": "192.168.1.11"}},
        ]
        users = {
            "alice": {"id": "alice", "role": "user", "category": "c", "group": "g"},
            "bob": {"id": "bob", "role": "user", "category": "c", "group": "g"},
        }
        self._patch_db(simple_iptools, monkeypatch, desktops, users)
        entry = _entry("vpn1", "10.9.0.5/32", {"users": ["bob"]})

        with patch.object(simple_iptools, "check_output", _iptables_mock()) as run:
            uipt.refresh_remotevpn_allowed(entry)

        # Both desktops are cleaned first, in both directions, so the operation
        # is idempotent whichever way the permission moved...
        assert _rules(run.mock_calls, "-D") == [
            ("192.168.1.10", "10.9.0.5/32"),
            ("10.9.0.5/32", "192.168.1.10"),
            ("192.168.1.11", "10.9.0.5/32"),
            ("10.9.0.5/32", "192.168.1.11"),
        ]
        # ...and only bob, who is still allowed, gets the rule back.
        assert _rules(run.mock_calls, "-A") == [
            ("192.168.1.11", "10.9.0.5/32"),
            ("10.9.0.5/32", "192.168.1.11"),
        ]

    def test_a_desktop_without_a_guest_ip_is_skipped(self, simple_iptools, monkeypatch):
        uipt = _uipt(simple_iptools)
        desktops = [{"id": "d1", "user": "alice", "viewer": {}}]
        users = {
            "alice": {"id": "alice", "role": "user", "category": "c", "group": "g"}
        }
        self._patch_db(simple_iptools, monkeypatch, desktops, users)

        with patch.object(simple_iptools, "check_output", _iptables_mock()) as run:
            uipt.refresh_remotevpn_allowed(_entry("v", "10.9.0.5/32", {"users": []}))

        run.assert_not_called()

    def test_each_user_is_read_once_however_many_desktops_they_have(
        self, simple_iptools, monkeypatch
    ):
        uipt = _uipt(simple_iptools)
        desktops = [
            {
                "id": "d%d" % i,
                "user": "alice",
                "viewer": {"guest_ip": "192.168.1.%d" % i},
            }
            for i in range(3)
        ]
        reads = []

        def table(name):
            class _Q:
                def get_all(self, *a, **k):
                    return self

                def pluck(self, *a, **k):
                    return self

                def get(self, key):
                    reads.append(key)
                    return self

                def run(self, conn):
                    if name == "domains":
                        return list(desktops)
                    return {"id": "alice", "role": "u", "category": "c", "group": "g"}

            return _Q()

        monkeypatch.setattr(simple_iptools.r, "table", table)

        with patch.object(simple_iptools, "check_output", _iptables_mock()):
            uipt.refresh_remotevpn_allowed(_entry("v", "10.9.0.5/32", {"users": []}))

        assert reads == ["alice"]
