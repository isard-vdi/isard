#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the adaptive poll cadence in ``tunnel_monitor._poll_once``."""

from isardvdi_vpn import tunnel_monitor


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


def test_coming_up_past_window_clears_tracker(monkeypatch):
    rows = [{"id": "h2"}]
    tracker = {"h2": 1000.0}
    # connected, and the fast-follow window has fully elapsed -> clear
    _patch(monkeypatch, {"h2": True}, [1000.0 + tunnel_monitor.FAST_FOLLOW_S + 1])
    fast = tunnel_monitor._poll_once(_FakeR(rows), None, True, tracker)
    assert fast is False
    assert tracker == {}


def test_flap_within_window_keeps_anchor(monkeypatch):
    """A brief reconnect inside the window must NOT clear the anchor, so a
    flapping hypervisor can't re-arm a fresh fast window on every flap."""
    rows = [{"id": "h2"}]
    first_seen = 1000.0
    tracker = {"h2": first_seen}
    # connected, but only 2 s into the 60 s window -> anchor kept
    _patch(monkeypatch, {"h2": True}, [first_seen + 2.0])
    fast = tunnel_monitor._poll_once(_FakeR(rows), None, True, tracker)
    assert fast is False
    assert tracker == {"h2": first_seen}


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


def test_wireguard_handshake_window_survives_rekey(monkeypatch):
    """A healthy wg tunnel rekeys ~every 120s, so latest_handshake ages to
    ~120s; the window must not report it disconnected before REJECT_AFTER_TIME."""
    monkeypatch.setattr(tunnel_monitor.time, "time", lambda: 1000.0)
    # 100s-old handshake (past the old 75s window, still mid healthy cycle)
    assert tunnel_monitor._connected_wireguard("PUB", {"PUB": 900.0}) is True
    # 190s-old: peer genuinely stopped handshaking -> disconnected
    assert tunnel_monitor._connected_wireguard("PUB", {"PUB": 810.0}) is False
    # never handshaked
    assert tunnel_monitor._connected_wireguard("PUB", {}) is False


class _Ensure:
    """Records ensure_port calls and answers with the next scripted result."""

    def __init__(self, results):
        self.results = list(results)
        self.calls = []

    def __call__(self, hyper_id, hostname):
        self.calls.append((hyper_id, hostname))
        return self.results.pop(0) if self.results else True


def _patch_ports(monkeypatch, ports, clock):
    """ports: hyper id -> bfd state, None when the OVS port does not exist."""
    monkeypatch.setattr(tunnel_monitor, "_bfd_state", lambda hid: ports.get(hid))
    monkeypatch.setattr(
        tunnel_monitor, "_set_status", lambda r, conn, hid, connected: None
    )
    monkeypatch.setattr(tunnel_monitor.time, "monotonic", lambda: clock[0])


def test_missing_geneve_port_is_created(monkeypatch):
    """The hypervisor was not running when the port was first wanted: the
    monitor creates it on its own instead of waiting for a row change."""
    rows = [{"id": "h1", "hostname": "isard-hypervisor"}]
    _patch_ports(monkeypatch, {}, [1000.0])
    ensure = _Ensure([True])
    tunnel_monitor._poll_once(_FakeR(rows), None, True, {}, ensure, {})
    assert ensure.calls == [("h1", "isard-hypervisor")]


def test_tunnel_that_is_up_is_left_alone(monkeypatch):
    rows = [{"id": "h1", "hostname": "isard-hypervisor"}]
    _patch_ports(monkeypatch, {"h1": "up"}, [1000.0])
    ensure = _Ensure([])
    tunnel_monitor._poll_once(_FakeR(rows), None, True, {}, ensure, {})
    assert ensure.calls == []


def test_port_creation_is_not_attempted_outside_geneve_only(monkeypatch):
    rows = [
        {
            "id": "h1",
            "hostname": "isard-hypervisor",
            "vpn": {"tunneling_mode": "geneve"},
        }
    ]
    _patch_ports(monkeypatch, {}, [1000.0])
    monkeypatch.setattr(tunnel_monitor, "_wg_handshakes", lambda i: {})
    ensure = _Ensure([])
    tunnel_monitor._poll_once(_FakeR(rows), None, False, {}, ensure, {})
    assert ensure.calls == []


def test_failed_port_creation_backs_off(monkeypatch):
    """A hostname that never resolves (a host gone for good) is retried with a
    doubling wait, not on every poll."""
    rows = [{"id": "h1", "hostname": "gone"}]
    clock = [1000.0]
    _patch_ports(monkeypatch, {}, clock)
    ensure = _Ensure([False] * 20)
    attempts: dict = {}

    def poll_at(t):
        clock[0] = t
        tunnel_monitor._poll_once(_FakeR(rows), None, True, {}, ensure, attempts)

    poll_at(1000.0)
    assert len(ensure.calls) == 1
    poll_at(1000.0 + tunnel_monitor.ENSURE_PORT_RETRY_S - 1)
    assert len(ensure.calls) == 1, "retried before the wait elapsed"
    poll_at(1000.0 + tunnel_monitor.ENSURE_PORT_RETRY_S)
    assert len(ensure.calls) == 2
    # the second wait is twice the first
    poll_at(1000.0 + 3 * tunnel_monitor.ENSURE_PORT_RETRY_S - 1)
    assert len(ensure.calls) == 2
    poll_at(1000.0 + 3 * tunnel_monitor.ENSURE_PORT_RETRY_S)
    assert len(ensure.calls) == 3
    # and it is capped
    for _ in range(10):
        poll_at(attempts["h1"][0])
    assert attempts["h1"][1] == tunnel_monitor.ENSURE_PORT_RETRY_MAX_S


def test_port_creation_error_does_not_skip_the_status(monkeypatch):
    rows = [{"id": "h1", "hostname": "isard-hypervisor"}]
    _patch_ports(monkeypatch, {}, [1000.0])
    written = []
    monkeypatch.setattr(
        tunnel_monitor,
        "_set_status",
        lambda r, conn, hid, connected: written.append((hid, connected)),
    )

    def boom(hyper_id, hostname):
        raise RuntimeError("ovs-vsctl failed")

    attempts: dict = {}
    tunnel_monitor._poll_once(_FakeR(rows), None, True, {}, boom, attempts)
    assert written == [("h1", False)]
    assert "h1" in attempts


def test_vanished_hypervisor_is_pruned_from_port_attempts(monkeypatch):
    rows = [{"id": "h1", "hostname": "isard-hypervisor"}]
    _patch_ports(monkeypatch, {"h1": "up"}, [1000.0])
    attempts = {"h_gone": (2000.0, 20.0)}
    tunnel_monitor._poll_once(_FakeR(rows), None, True, {}, _Ensure([]), attempts)
    assert attempts == {}


def test_hypervisor_recreated_with_a_new_address_is_followed(monkeypatch):
    """The port exists but points at the old address, so BFD stays down: the
    monitor must re-run the ensure, which resolves the hostname again."""
    from unittest.mock import patch

    from isardvdi_vpn import wgadmin

    rows = [{"id": "h1", "hostname": "isard-hypervisor"}]
    clock = [1000.0]
    _patch_ports(monkeypatch, {"h1": "down"}, clock)
    monkeypatch.setenv("WG_HYPERS_PORT", "4443")
    addresses = iter(["192.0.2.10", "192.0.2.20"])
    monkeypatch.setattr(wgadmin.socket, "gethostbyname", lambda h: next(addresses))
    attempts: dict = {}
    with patch.object(wgadmin, "check_output", return_value="1"), patch.object(
        wgadmin, "subprocess"
    ) as sp:
        tunnel_monitor._poll_once(
            _FakeR(rows), None, True, {}, wgadmin.ensure_geneve_port, attempts
        )
        clock[0] += tunnel_monitor.ENSURE_PORT_RETRY_S
        tunnel_monitor._poll_once(
            _FakeR(rows), None, True, {}, wgadmin.ensure_geneve_port, attempts
        )
    remote_ips = [
        a for c in sp.run.call_args_list for a in c.args[0] if "remote_ip=" in a
    ]
    assert remote_ips == [
        "options:remote_ip=192.0.2.10",
        "options:remote_ip=192.0.2.20",
    ]


def test_successful_ensure_on_a_down_tunnel_is_not_repeated_every_poll(monkeypatch):
    rows = [{"id": "h1", "hostname": "isard-hypervisor"}]
    clock = [1000.0]
    _patch_ports(monkeypatch, {"h1": "down"}, clock)
    ensure = _Ensure([True] * 5)
    attempts: dict = {}
    for _ in range(5):
        tunnel_monitor._poll_once(_FakeR(rows), None, True, {}, ensure, attempts)
        clock[0] += 1
    assert len(ensure.calls) == 1


def test_attempts_reset_when_the_tunnel_comes_up(monkeypatch):
    rows = [{"id": "h1", "hostname": "isard-hypervisor"}]
    ports = {"h1": "down"}
    _patch_ports(monkeypatch, ports, [1000.0])
    attempts: dict = {}
    tunnel_monitor._poll_once(_FakeR(rows), None, True, {}, _Ensure([True]), attempts)
    assert "h1" in attempts
    ports["h1"] = "up"
    tunnel_monitor._poll_once(_FakeR(rows), None, True, {}, _Ensure([]), attempts)
    assert attempts == {}


def test_removed_hypervisor_is_not_ensured_again(monkeypatch):
    """A hypervisor deleted from the table must not get its port back."""
    _patch_ports(monkeypatch, {}, [1000.0])
    ensure = _Ensure([False])
    attempts: dict = {}
    tunnel_monitor._poll_once(
        _FakeR([{"id": "h1", "hostname": "isard-hypervisor"}]),
        None,
        True,
        {},
        ensure,
        attempts,
    )
    tunnel_monitor._poll_once(_FakeR([]), None, True, {}, ensure, attempts)
    assert ensure.calls == [("h1", "isard-hypervisor")]
    assert attempts == {}
