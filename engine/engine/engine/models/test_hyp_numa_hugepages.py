# Copyright 2026 the Isard-vdi project authors:
#      Josep Maria Viñolas Auquer
# License: AGPLv3

"""Pin the per-NUMA hugepages stats refresh in hyp._get_hugepages_stats.

f319cc3e5 introduced ``numa_hugepages_free_kb`` as the per-stats-cycle
output of the engine: ``ui_actions`` reads it from ``extra_info`` to pick
the NUMA node with the most free hugepages for non-GPU desktops and to
weight ``mem_mode=strict`` vs ``preferred`` for GPU desktops. Falls back
to a hash-distributed node pick when empty.

Three production paths to pin:
  1. Multi-NUMA host with sysfs reachable → returns total + per-NUMA dict.
  2. Single-NUMA host (or per-NUMA sysfs failure) → falls back to global
     sysfs read, returns total + empty per-NUMA dict.
  3. Sysfs entirely unavailable → falls back to libvirt ``getFreePages``
     with the duplicate-cell-id collision guard, returns total + empty.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest

from engine.models import hyp as hyp_mod
from engine.models.hyp import hyp


class _FakeSSHTimeoutError(Exception):
    """Real exception class so the production ``except (SSHTimeoutError,
    Exception)`` block accepts it under pytest, where the imported symbol
    is otherwise a ``MagicMock`` via conftest.py's ``engine.services.lib.
    functions`` stub."""


def _real_cpu_stats(*_args, **_kwargs):
    """Stub for ``calcule_cpu_hyp_stats`` (a 3-tuple is unpacked by
    ``HypStats.set_stats``). The stubbed conftest version returns an empty
    MagicMock which fails the unpack — return a real 3-tuple instead."""
    return ({"kernel": 0, "user": 0, "idle": 100, "iowait": 0}, 0, 0)


@pytest.fixture(autouse=True)
def _bootstrap(monkeypatch):
    """``engine.services.log`` and ``engine.services.lib.functions`` are
    stubbed by ``engine/engine/conftest.py``, so the module-level ``log``,
    ``logs``, ``SSHTimeoutError`` and ``calcule_cpu_hyp_stats`` symbols
    pulled in via star-import are MagicMocks. Inject real (or
    real-shaped) replacements only for the duration of each test so the
    production code paths exercise without surprise TypeError /
    ValueError under pytest."""
    fake_log = logging.getLogger(__name__)
    monkeypatch.setattr(hyp_mod, "log", fake_log, raising=False)
    fake_logs = MagicMock()
    fake_logs.main = fake_log
    monkeypatch.setattr(hyp_mod, "logs", fake_logs, raising=False)
    monkeypatch.setattr(hyp_mod, "SSHTimeoutError", _FakeSSHTimeoutError, raising=False)
    monkeypatch.setattr(
        hyp_mod, "calcule_cpu_hyp_stats", _real_cpu_stats, raising=False
    )


def _build_hyp(numa_nodes=None, hugepages_info=None):
    """Construct a hyp bypassing __init__ (libvirt/ssh/threads). The tests
    only exercise ``_get_hugepages_stats`` and friends against the
    pre-populated ``hypervisor`` dict."""
    h = hyp.__new__(hyp)
    h.id_hyp_rethink = "isard-hypervisor"
    h.hostname = "isard-hypervisor"
    h.user = "root"
    h.port = "2022"
    h.hypervisor = {
        "hugepages_info": hugepages_info
        or {"1G": {"total": 0}, "2M": {"total": 8}, "mounted": True},
        "numa_topology": {"nodes": {n: {"cpulist": "0-3"} for n in (numa_nodes or [])}},
    }
    return h


# ── _get_hugepages_free_from_sysfs (the new helper) ────────────────────────


def _ssh_result(out, err=b""):
    return {"out": out.encode() if isinstance(out, str) else out, "err": err}


@patch("engine.models.hyp.exec_remote_cmd")
def test_per_numa_sysfs_read_returns_dict(mock_ssh):
    """Multi-NUMA host: the per-node SSH read produces a dict keyed by node id."""
    h = _build_hyp(numa_nodes=["0", "1"])
    # 1G total=0 → only 2M (2048 KB) is queried. 4 cells expected:
    # 2 nodes × 1 size = 2 reads → output has 2 parts separated by "---".
    # The helper sees 4 expected if 1G+2M both queried. Here only 2M.
    mock_ssh.return_value = _ssh_result(
        "32\n---\n16"
    )  # 32 free 2M on node0, 16 on node1
    total, per_numa = h._get_hugepages_free_from_sysfs(0, 8)
    assert per_numa == {"0": 32 * 2048, "1": 16 * 2048}
    assert total == 32 * 2048 + 16 * 2048


@patch("engine.models.hyp.exec_remote_cmd")
def test_single_numa_falls_through_to_global(mock_ssh):
    """Single NUMA cell: the per-node branch is skipped; the global sysfs
    read fires once. Returned per_numa dict is empty."""
    h = _build_hyp(numa_nodes=["0"])  # only one node → skip per-numa
    mock_ssh.return_value = _ssh_result("64")  # 64 free 2M total
    total, per_numa = h._get_hugepages_free_from_sysfs(0, 8)
    assert per_numa == {}
    assert total == 64 * 2048


@patch("engine.models.hyp.exec_remote_cmd")
def test_per_numa_failure_falls_back_to_global(mock_ssh):
    """If the per-NUMA SSH command returns an error, the helper retries
    with the global-only command and returns an empty per_numa dict."""
    h = _build_hyp(numa_nodes=["0", "1"])
    # First call (per-NUMA): err set. Second call (global): success.
    mock_ssh.side_effect = [
        _ssh_result("", err=b"cat: No such file or directory"),
        _ssh_result("48"),
    ]
    total, per_numa = h._get_hugepages_free_from_sysfs(0, 8)
    assert per_numa == {}
    assert total == 48 * 2048
    assert mock_ssh.call_count == 2


@patch("engine.models.hyp.exec_remote_cmd")
def test_sysfs_exception_returns_none(mock_ssh):
    """Any SSH-layer exception surfaces as ``(None, {})`` so the caller
    falls back to libvirt ``getFreePages``."""
    h = _build_hyp(numa_nodes=["0", "1"])
    mock_ssh.side_effect = Exception("ssh dead")
    total, per_numa = h._get_hugepages_free_from_sysfs(0, 8)
    assert (total, per_numa) == (None, {})


# ── _get_hugepages_stats (the 3-tuple return contract) ─────────────────────


@patch("engine.models.hyp.exec_remote_cmd")
def test_hugepages_stats_zero_when_no_hugepages_configured(mock_ssh):
    """``hugepages_info`` with all totals=0 returns (0, 0, {}) without any
    SSH call (early return)."""
    h = _build_hyp(hugepages_info={"1G": {"total": 0}, "2M": {"total": 0}})
    total, free, per_numa = h._get_hugepages_stats()
    assert (total, free, per_numa) == (0, 0, {})
    mock_ssh.assert_not_called()


@patch("engine.models.hyp.exec_remote_cmd")
def test_hugepages_stats_primary_sysfs_wins(mock_ssh):
    """When sysfs read succeeds, the libvirt fallback is not used (no
    ``conn.getFreePages`` is even attempted)."""
    h = _build_hyp(numa_nodes=["0", "1"])
    mock_ssh.return_value = _ssh_result("4\n---\n2")  # per-NUMA
    h.conn = MagicMock()
    total, free, per_numa = h._get_hugepages_stats()
    assert total == 8 * 2048  # 2M * 8 from hugepages_info
    assert free == 6 * 2048  # 4 + 2 pages from sysfs
    assert per_numa == {"0": 4 * 2048, "1": 2 * 2048}
    h.conn.getInfo.assert_not_called()
    h.conn.getFreePages.assert_not_called()


@patch("engine.models.hyp.exec_remote_cmd")
def test_hugepages_stats_libvirt_fallback_with_collision_guard(mock_ssh):
    """When sysfs fails entirely, the libvirt fallback fires. The guard
    re-queries with ``cellNum=1`` when the returned dict has fewer cells
    than ``num_cells`` (libvirt duplicate-cell-id bug)."""
    h = _build_hyp(numa_nodes=["0", "1"])
    mock_ssh.side_effect = Exception("ssh dead")
    h.conn = MagicMock()
    h.conn.getInfo.return_value = (None, None, None, None, 2)  # num_cells=2
    h.conn.getFreePages.side_effect = [
        {0: {2048: 1}},  # only 1 cell → triggers single-cell retry
        {0: {2048: 16}},  # single-cell query returns the true total
    ]
    total, free, per_numa = h._get_hugepages_stats()
    assert total == 8 * 2048
    # 16 free pages × 2048 KB = 32768 KB, but capped at total (16384)
    # via ``min(hugepages_free_kb, hugepages_total_kb)``.
    assert free == 8 * 2048
    assert per_numa == {}
    assert h.conn.getFreePages.call_count == 2
    # second call uses cellNum=1
    _, kwargs_or_args = h.conn.getFreePages.call_args
    assert h.conn.getFreePages.call_args[0][2] == 1  # cellNum positional


# ── HypStats.set_stats writes numa_hugepages_free_kb into memory ───────────


def test_set_stats_writes_numa_hugepages_free_kb():
    """``HypStats.set_stats`` must persist ``numa_hugepages_free_kb`` into
    the memory dict so consumers (``ui_actions``) see it through
    ``mem_stats``."""
    hyp_stats = hyp_mod.HypStats()
    memory = {"total": 16_000_000, "free": 8_000_000, "cached": 1_000_000}
    cpu = {"kernel": 0, "user": 0, "idle": 100, "iowait": 0}
    hyp_stats.set_stats(
        "isard-hypervisor",
        memory,
        cpu,
        hugepages_total_kb=8 * 2048,
        hugepages_free_kb=6 * 2048,
        numa_hugepages_free_kb={"0": 4 * 2048, "1": 2 * 2048},
    )
    # memory dict mutated in place
    assert memory["hugepages_total_kb"] == 8 * 2048
    assert memory["hugepages_free_kb"] == 6 * 2048
    assert memory["numa_hugepages_free_kb"] == {"0": 4 * 2048, "1": 2 * 2048}


def test_set_stats_numa_hugepages_default_empty_dict():
    """When ``numa_hugepages_free_kb`` is omitted (single-NUMA host or
    sysfs failed), the memory dict still has the key set to ``{}`` so
    consumers can ``memory.get(key, {})`` safely."""
    hyp_stats = hyp_mod.HypStats()
    memory = {"total": 16_000_000, "free": 8_000_000, "cached": 1_000_000}
    cpu = {"kernel": 0, "user": 0, "idle": 100, "iowait": 0}
    hyp_stats.set_stats("isard-hypervisor", memory, cpu)
    assert memory["numa_hugepages_free_kb"] == {}
