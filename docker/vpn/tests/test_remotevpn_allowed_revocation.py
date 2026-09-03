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

_ABSENT = object()

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


class TestMalformedAllowedIsNotOpen:
    """A malformed ``allowed`` must not read as "everybody".

    Only a real empty list means everybody. A level that is absent, null or not
    a list is a malformed row, and treating it as open hands every user an entry
    that names somebody else. The code this replaced raised KeyError on a missing
    level, which failed closed by crashing; failing closed quietly is better, but
    failing OPEN is not an option.
    """

    USER = {
        "id": "alice",
        "role": "user",
        "category": "cat",
        "group": "grp",
        "secondary_groups": ["grp2"],
    }

    @staticmethod
    def _entry(allowed):
        entry = {"id": "rv", "vpn": {"wireguard": {"Address": "10.9.0.5/32"}}}
        if allowed is not _ABSENT:
            entry["allowed"] = allowed
        return entry

    def test_a_level_naming_somebody_else_is_not_widened_by_the_missing_ones(
        self, simple_iptools
    ):
        # The one that matters: users names bob, and the three levels checked
        # before it are simply absent.
        entry = self._entry({"users": ["bob"]})
        assert (
            simple_iptools.UserIpTools.is_allowed_remotevpn(self.USER, entry) is False
        )

    def test_an_empty_allowed_grants_nothing(self, simple_iptools):
        assert (
            simple_iptools.UserIpTools.is_allowed_remotevpn(self.USER, self._entry({}))
            is False
        )

    def test_a_missing_allowed_grants_nothing(self, simple_iptools):
        assert (
            simple_iptools.UserIpTools.is_allowed_remotevpn(
                self.USER, self._entry(_ABSENT)
            )
            is False
        )

    def test_a_null_level_is_skipped_not_opened(self, simple_iptools):
        entry = self._entry(
            {"roles": None, "categories": False, "groups": False, "users": ["bob"]}
        )
        assert (
            simple_iptools.UserIpTools.is_allowed_remotevpn(self.USER, entry) is False
        )

    def test_a_level_that_is_not_a_list_is_skipped(self, simple_iptools):
        entry = self._entry(
            {"roles": "user", "categories": False, "groups": False, "users": ["bob"]}
        )
        assert (
            simple_iptools.UserIpTools.is_allowed_remotevpn(self.USER, entry) is False
        )

    def test_allowed_that_is_not_a_dict_does_not_raise(self, simple_iptools):
        for junk in ("notadict", [], 7):
            entry = {"id": "rv", "allowed": junk, "vpn": {"wireguard": {}}}
            assert (
                simple_iptools.UserIpTools.is_allowed_remotevpn(self.USER, entry)
                is False
            )

    def test_a_real_empty_list_still_means_everybody(self, simple_iptools):
        # The documented semantics must survive the hardening.
        entry = self._entry(
            {"roles": False, "categories": False, "groups": False, "users": []}
        )
        assert simple_iptools.UserIpTools.is_allowed_remotevpn(self.USER, entry) is True

    def test_a_secondary_group_still_grants(self, simple_iptools):
        entry = self._entry(
            {"roles": False, "categories": False, "groups": ["grp2"], "users": False}
        )
        assert simple_iptools.UserIpTools.is_allowed_remotevpn(self.USER, entry) is True


class TestOneFailureDoesNotStopTheSweep:
    """A refresh that gives up halfway leaves the leak it came to close.

    This is the revocation path: every desktop after the failure keeps reaching
    a host its user may no longer use. And the caller swallows what reaches it,
    so an aborted pass is invisible. Each desktop is isolated and the failures
    are counted and named.
    """

    DESKTOPS = [
        {
            "id": "d%d" % i,
            "user": "u%d" % i,
            "viewer": {"guest_ip": "10.2.0.%d" % (10 + i)},
        }
        for i in range(5)
    ]
    USERS = {
        "u%d" % i: {"id": "u%d" % i, "role": "user", "category": "c", "group": "g"}
        for i in range(5)
    }
    OPEN_TO_ALL = {
        "id": "rv",
        "allowed": {"roles": False, "categories": False, "groups": False, "users": []},
        "vpn": {"wireguard": {"Address": "10.9.0.5/32", "extra_client_nets": None}},
    }

    def _patch_db(self, module, monkeypatch):
        desktops, users = self.DESKTOPS, self.USERS

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
                    return list(desktops) if name == "domains" else users.get(self._key)

            return _Q()

        monkeypatch.setattr(module.r, "table", table)

    @staticmethod
    def _runner(fail_from=None):
        """A check_output that reports every rule absent, failing from call N."""
        state = {"n": 0, "touched": set()}

        def _run(argv, *args, **kwargs):
            state["n"] += 1
            if "-C" in argv:
                raise CalledProcessError(1, argv)
            for flag in ("-s", "-d"):
                value = argv[argv.index(flag) + 1]
                if value.startswith("10.2.0."):
                    state["touched"].add(value)
            if fail_from is not None and state["n"] >= fail_from:
                raise CalledProcessError(1, argv)
            return b""

        return _run, state

    def test_a_clean_pass_reaches_every_desktop(self, simple_iptools, monkeypatch):
        uipt = _uipt(simple_iptools)
        self._patch_db(simple_iptools, monkeypatch)
        runner, state = self._runner()
        with patch.object(simple_iptools, "check_output", runner):
            failed = uipt.refresh_remotevpn_allowed(self.OPEN_TO_ALL)
        assert len(state["touched"]) == 5
        assert failed == []

    def test_one_failure_does_not_cost_the_desktops_behind_it(
        self, simple_iptools, monkeypatch
    ):
        uipt = _uipt(simple_iptools)
        self._patch_db(simple_iptools, monkeypatch)
        runner, state = self._runner(fail_from=6)
        with patch.object(simple_iptools, "check_output", runner):
            failed = uipt.refresh_remotevpn_allowed(self.OPEN_TO_ALL)
        # Every desktop is still attempted, and the ones that failed are named.
        assert len(state["touched"]) == 5, state["touched"]
        assert failed, "a failed desktop must be reported, not swallowed"

    def test_an_unreadable_user_does_not_stop_the_others(
        self, simple_iptools, monkeypatch
    ):
        uipt = _uipt(simple_iptools)
        desktops, users = self.DESKTOPS, self.USERS

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
                    if self._key == "u2":
                        raise RuntimeError("row unreadable")
                    return users.get(self._key)

            return _Q()

        monkeypatch.setattr(simple_iptools.r, "table", table)
        runner, state = self._runner()
        with patch.object(simple_iptools, "check_output", runner):
            uipt.refresh_remotevpn_allowed(self.OPEN_TO_ALL)
        # Four of the five still get their rules; only u2's desktop is skipped.
        assert len(state["touched"]) == 4, state["touched"]
