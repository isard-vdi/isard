# Copyright the Isard-vdi project authors:
# License: AGPLv3

"""The hypervisor stats carry the configured memory of the running guests."""

import logging
import time
from unittest.mock import MagicMock

import pytest

from engine.models import hyp as hyp_mod
from engine.models.hyp import HypStats, hyp

GIB = 1048576


def _real_cpu_stats(*_args, **_kwargs):
    return ({"kernel": 0, "user": 0, "idle": 100, "iowait": 0}, 0, 0)


@pytest.fixture(autouse=True)
def _bootstrap(monkeypatch):
    monkeypatch.setattr(hyp_mod, "log", logging.getLogger(__name__), raising=False)
    monkeypatch.setattr(
        hyp_mod, "calcule_cpu_hyp_stats", _real_cpu_stats, raising=False
    )


def _build_hyp(conn):
    h = hyp.__new__(hyp)
    h.id_hyp_rethink = "isard-hypervisor"
    h.conn = conn
    return h


def test_guests_memory_sums_the_configured_memory_of_running_guests():
    conn = MagicMock()
    conn.getAllDomainStats.return_value = [
        (MagicMock(), {"balloon.maximum": 8 * GIB, "balloon.current": 2 * GIB}),
        (MagicMock(), {"balloon.current": 4 * GIB}),
        (MagicMock(), {}),
    ]
    assert _build_hyp(conn)._get_guests_memory_kb() == 12 * GIB


def test_guests_memory_is_none_when_libvirt_does_not_answer():
    conn = MagicMock()
    conn.getAllDomainStats.side_effect = RuntimeError("libvirt gone")
    assert _build_hyp(conn)._get_guests_memory_kb() is None


def _memory(free_gb):
    return {"total": 64 * GIB, "free": free_gb * GIB, "cached": 0, "buffers": 0}


def _cpu():
    return {"kernel": 0, "user": 0, "idle": 0, "iowait": 0}


def test_set_stats_stores_guests_memory_only_when_known():
    stats = HypStats()
    stats.set_stats("h", _memory(10), _cpu(), guests_kb=20 * GIB)
    assert stats.get_stats("h")["memory"]["guests_kb"] == 20 * GIB
    stats = HypStats()
    stats.set_stats("h", _memory(10), _cpu())
    assert "guests_kb" not in stats.get_stats("h")["memory"]


def test_a_window_with_samples_missing_guests_memory_still_averages():
    stats = HypStats()
    now = time.time()
    stats.hyper_stats_history["h"] = {
        now - 30: {"memory": {"total": 1, "guests_kb": 10}, "cpu": _cpu()},
        now - 20: {"memory": {"total": 1}, "cpu": _cpu()},
        now - 10: {"memory": {"total": 1, "guests_kb": 20}, "cpu": _cpu()},
    }
    assert stats.get_stats("h", minutes=1)["memory"]["guests_kb"] == 15
