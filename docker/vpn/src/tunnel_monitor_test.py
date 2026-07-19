#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the adaptive poll cadence in ``tunnel_monitor._poll_once``.

Deps (``rethinkdb``) only exist in the isard-vpn image:
``PYTHONPATH=/src pytest tunnel_monitor_test.py``.
"""

import tunnel_monitor


class _FakeQuery:
    def __init__(self, rows):
        self._rows = rows

    def pluck(self, *a, **k):
        return self

    def run(self, conn):
        return list(self._rows)


class _FakeR:
    def __init__(self, rows):
        self._rows = rows

    def table(self, name):
        return _FakeQuery(self._rows)


def _patch(monkeypatch, connected_by_id, clock):
    """Stub out the OVS/DB side-effects so only the cadence logic is exercised."""
    monkeypatch.setattr(
        tunnel_monitor, "_connected_geneve", lambda hid: connected_by_id[hid]
    )
    monkeypatch.setattr(
        tunnel_monitor, "_set_status", lambda r, conn, hid, connected: None
    )
    monkeypatch.setattr(tunnel_monitor.time, "monotonic", lambda: clock[0])


def test_all_connected_is_slow(monkeypatch):
    rows = [{"id": "h1"}, {"id": "h2"}]
    _patch(monkeypatch, {"h1": True, "h2": True}, [1000.0])
    tracker: dict[str, float] = {}
    fast = tunnel_monitor._poll_once(_FakeR(rows), None, True, tracker)
    assert fast is False
    assert tracker == {}


def test_fresh_disconnect_is_fast(monkeypatch):
    rows = [{"id": "h1"}, {"id": "h2"}]
    _patch(monkeypatch, {"h1": True, "h2": False}, [1000.0])
    tracker: dict[str, float] = {}
    fast = tunnel_monitor._poll_once(_FakeR(rows), None, True, tracker)
    assert fast is True
    assert tracker == {"h2": 1000.0}


def test_coming_up_clears_tracker_and_goes_slow(monkeypatch):
    rows = [{"id": "h2"}]
    tracker = {"h2": 1000.0}
    _patch(monkeypatch, {"h2": True}, [1002.0])
    fast = tunnel_monitor._poll_once(_FakeR(rows), None, True, tracker)
    assert fast is False
    assert tracker == {}


def test_long_dead_hypervisor_falls_back_to_slow(monkeypatch):
    """A hypervisor down past FAST_FOLLOW_S must not pin the loop fast."""
    rows = [{"id": "h2"}]
    first_seen = 1000.0
    tracker = {"h2": first_seen}
    clock = [first_seen + tunnel_monitor.FAST_FOLLOW_S + 1]
    _patch(monkeypatch, {"h2": False}, clock)
    fast = tunnel_monitor._poll_once(_FakeR(rows), None, True, tracker)
    assert fast is False
    # still tracked (it is still down), just no longer fast-followed
    assert tracker == {"h2": first_seen}


def test_vanished_hypervisor_is_pruned(monkeypatch):
    rows = [{"id": "h1"}]
    tracker = {"h_gone": 500.0}
    _patch(monkeypatch, {"h1": True}, [1000.0])
    fast = tunnel_monitor._poll_once(_FakeR(rows), None, True, tracker)
    assert fast is False
    assert tracker == {}
