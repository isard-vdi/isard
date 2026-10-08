"""The broom when some hypervisor checks block inside libvirt."""

import sys
import threading
import time
from unittest.mock import MagicMock

import pytest

try:
    import engine.models.hyp  # noqa: F401
except Exception:
    sys.modules["engine.models.hyp"] = MagicMock()

from engine.controllers import broom  # noqa: E402

HUNG = ["hung-1", "hung-2", "hung-3"]
HEALTHY = ["healthy-1", "healthy-2"]


@pytest.fixture(autouse=True)
def storage_probe(monkeypatch):
    probe = MagicMock(return_value={"out": b"", "err": b""})
    monkeypatch.setattr(broom, "exec_remote_cmd", probe, raising=False)
    monkeypatch.setattr(broom, "_storage_hung", {}, raising=False)
    return probe


def _connected(monkeypatch, domains=None, disk_usage=None):
    h = MagicMock()
    h.connected = True
    h.get_domains.return_value = domains or {}
    h.get_storage_used.return_value = disk_usage or []
    monkeypatch.setattr(broom, "hyp", MagicMock(return_value=h))
    monkeypatch.setattr(
        broom,
        "get_hyp_hostname_from_id",
        lambda hyp_id: ("host", 22, "root", False, None),
    )
    monkeypatch.setattr(broom, "update_table_dict", MagicMock())
    return h


@pytest.fixture
def fast_broom(monkeypatch):
    monkeypatch.setattr(broom, "BROOM_HYP_TIMEOUT", 0.3)
    monkeypatch.setattr(broom, "BROOM_MAX_WORKERS", 4)
    release = threading.Event()
    calls = {}

    def fake_check(hyp_id, disk_interval, started_ids):
        calls[hyp_id] = calls.get(hyp_id, 0) + 1
        if hyp_id in HUNG:
            release.wait(30)
        return {
            "hyp_id": hyp_id,
            "success": True,
            "active_domains": {},
            "domains_destroyed": [],
            "domains_handled": [],
            "error": None,
        }

    degraded = MagicMock()
    monkeypatch.setattr(broom, "_check_single_hypervisor", fake_check)
    monkeypatch.setattr(broom, "update_hyp_degraded_status", degraded)
    monkeypatch.setattr(broom, "update_hyp_libvirt_warning", MagicMock())
    monkeypatch.setattr(broom, "get_degraded_hyp_ids", lambda: set())
    b = broom.ThreadBroom("broom-test", 1, MagicMock())
    yield b, degraded, calls, release
    release.set()
    b.stop_thread()


def _degraded_true(degraded):
    return {
        c.args[0]
        for c in degraded.call_args_list
        if c.kwargs.get("is_degraded") is True
    }


def test_healthy_hypervisors_are_never_degraded_by_stuck_ones(fast_broom):
    b, degraded, _, _ = fast_broom
    for _ in range(6):
        b._check_hypervisors_concurrent(HUNG + HEALTHY, 2, set())
    assert _degraded_true(degraded) == set(HUNG)


def test_a_stuck_check_is_not_submitted_again(fast_broom):
    b, _, calls, _ = fast_broom
    for _ in range(6):
        b._check_hypervisors_concurrent(HUNG + HEALTHY, 2, set())
    for hyp_id in HUNG:
        assert calls[hyp_id] == 1
    for hyp_id in HEALTHY:
        assert calls[hyp_id] == 6


def test_healthy_hypervisors_keep_reporting_domains(fast_broom):
    b, _, _, _ = fast_broom
    for _ in range(6):
        seen = b._check_hypervisors_concurrent(HUNG + HEALTHY, 2, set())
    assert set(seen) == set(HEALTHY)


def test_a_hypervisor_recovers_once_its_check_unblocks(fast_broom):
    b, degraded, calls, release = fast_broom
    b._check_hypervisors_concurrent(HUNG + HEALTHY, 2, set())
    b._check_hypervisors_concurrent(HUNG + HEALTHY, 2, set())
    assert _degraded_true(degraded) == set(HUNG)
    release.set()
    time.sleep(0.2)
    seen = b._check_hypervisors_concurrent(HUNG + HEALTHY, 2, set())
    assert set(seen) == set(HUNG + HEALTHY)
    recovered = {
        c.args[0]
        for c in degraded.call_args_list
        if c.kwargs.get("is_degraded") is False
    }
    assert recovered == set(HUNG)


@pytest.mark.parametrize(
    "libvirt_state,expected",
    [
        ({"status": "Paused", "detail": "paused due to disk I/O error"}, "Paused"),
        ({"status": "Started", "detail": "booted"}, "Started"),
    ],
)
def test_first_loop_publishes_the_state_libvirt_reports(
    monkeypatch, libvirt_state, expected
):
    h = MagicMock()
    h.connected = True
    h.get_domains.return_value = {"dom-1": libvirt_state}
    monkeypatch.setattr(broom, "hyp", MagicMock(return_value=h))
    monkeypatch.setattr(
        broom,
        "get_hyp_hostname_from_id",
        lambda hyp_id: ("host", 22, "root", False, None),
    )
    monkeypatch.setattr(broom, "get_domain_status", lambda domain_id: "Stopped")
    updated = MagicMock()
    monkeypatch.setattr(broom, "update_domain_hyp_started", updated)
    monkeypatch.setattr(broom, "update_table_dict", MagicMock())

    result = broom._check_single_hypervisor("hyp-1", 2, set())

    assert result["success"] is True
    assert updated.call_count == 1
    assert updated.call_args.args[0] == "dom-1"
    assert updated.call_args.args[-1] == expected


@pytest.mark.parametrize(
    "disk_usage,stored",
    [(False, []), ([{"mount": "/", "usage": 10}], [[{"mount": "/", "usage": 10}]])],
)
def test_unreadable_disk_usage_is_not_stored(monkeypatch, disk_usage, stored):
    h = MagicMock()
    h.connected = True
    h.get_domains.return_value = {}
    h.get_storage_used.return_value = disk_usage
    monkeypatch.setattr(broom, "hyp", MagicMock(return_value=h))
    monkeypatch.setattr(
        broom,
        "get_hyp_hostname_from_id",
        lambda hyp_id: ("host", 22, "root", False, None),
    )
    written = MagicMock()
    monkeypatch.setattr(broom, "update_table_dict", written)

    result = broom._check_single_hypervisor("hyp-1", 1, set())

    assert result["success"] is True
    assert [c.args[2]["mountpoints"] for c in written.call_args_list] == stored


def test_a_hung_storage_mount_fails_the_check(monkeypatch, storage_probe):
    h = _connected(monkeypatch)
    storage_probe.return_value = {"out": b"/isard/groups\n", "err": b""}

    result = broom._check_single_hypervisor("hyp-1", 1, set())

    assert result["success"] is False
    assert "/isard/groups" in result["error"]
    h.get_domains.assert_not_called()
    h.get_storage_used.assert_not_called()


def test_the_verdict_holds_between_probes(monkeypatch, storage_probe):
    _connected(monkeypatch)
    storage_probe.return_value = {"out": b"/isard/groups\n", "err": b""}
    assert broom._check_single_hypervisor("hyp-1", 1, set())["success"] is False

    storage_probe.return_value = {"out": b"", "err": b""}
    assert broom._check_single_hypervisor("hyp-1", 2, set())["success"] is False
    assert storage_probe.call_count == 1

    assert broom._check_single_hypervisor("hyp-1", 7, set())["success"] is True
    assert storage_probe.call_count == 2


def test_a_probe_that_cannot_run_fails_the_check(monkeypatch, storage_probe):
    _connected(monkeypatch)
    storage_probe.side_effect = TimeoutError("ssh timed out")

    result = broom._check_single_hypervisor("hyp-1", 1, set())

    assert result["success"] is False
    assert "storage not responding" in result["error"]
