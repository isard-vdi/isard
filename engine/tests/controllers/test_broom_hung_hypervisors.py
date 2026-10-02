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
