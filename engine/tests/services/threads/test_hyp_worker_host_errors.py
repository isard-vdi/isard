"""A hypervisor whose own system fails every start is degraded, not fed more.

When the host's root goes read-only, libvirt still answers: each start fails
at once, so no timeout ever fires and, without this, the balancer keeps
placing desktops there. Errors of the domain itself never count.
"""

import queue
from unittest.mock import MagicMock

import pytest
from libvirt import (
    VIR_ERR_CONFIG_UNSUPPORTED,
    VIR_ERR_INTERNAL_ERROR,
    VIR_ERR_OPERATION_INVALID,
    VIR_ERR_SYSTEM_ERROR,
    libvirtError,
)

from engine.services.lib import domain_guard
from engine.services.lib.libvirt_timeout import LibvirtOperationStats
from engine.services.threads import hyp_worker_thread as mod
from engine.services.threads.hyp_worker_thread import HypWorkerThread

READ_ONLY = (
    "Failed to create file '/var/lib/libvirt/dnsmasq/virbr0.macs.new': "
    "Read-only file system"
)
IDE = (
    "unsupported configuration: IDE controllers are unsupported for this "
    "QEMU binary or machine type"
)


def _error(code, message):
    error = libvirtError(message)
    error.err = (code, 0, message, 2, None, None, None, 0, 0)
    return error


@pytest.fixture
def env(monkeypatch):
    """Every libvirt call raises what the test puts in ``raising``; every
    degraded write and domain status write is recorded."""
    raising = {"error": None}

    def execute(func, args=(), kwargs=None, **_):
        if raising["error"] is not None:
            raise raising["error"]
        return MagicMock()

    degraded = []
    statuses = []
    monkeypatch.setattr(mod, "execute_with_timeout", execute)
    monkeypatch.setattr(
        mod,
        "update_hyp_degraded_status",
        lambda hyp_id, is_degraded, reason=None, source=None: degraded.append(
            (hyp_id, is_degraded, reason, source)
        ),
    )
    monkeypatch.setattr(mod, "update_hyp_libvirt_warning", MagicMock())
    monkeypatch.setattr(
        mod,
        "update_domain_status",
        lambda status, domain_id, **kw: statuses.append((status, domain_id)),
    )
    for name in ("log_action", "update_vgpu_info_if_stopped", "live_xml_cache"):
        monkeypatch.setattr(mod, name, MagicMock())
    monkeypatch.setattr(domain_guard, "_mirror", lambda *a: None)
    domain_guard._held.clear()
    yield raising, degraded, statuses
    domain_guard._held.clear()


def _worker():
    w = HypWorkerThread.__new__(HypWorkerThread)
    w.hyp_id = "hyp-1"
    w.hostname = "hyp-1"
    w.stop = False
    w.degraded = False
    w.degraded_since = None
    w.libvirt_stats = LibvirtOperationStats("hyp-1")
    w.queue_master = queue.Queue()
    w.queue_actions = queue.Queue()
    w.h = MagicMock()
    w.viewer = {}
    w._inflight_calls = {}
    w._cleanup_queued_actions = MagicMock()
    w._is_old_ovs_hypervisor = lambda: False
    return w


def _call(w, times):
    for _ in range(times):
        with pytest.raises(libvirtError):
            w._execute_libvirt_with_timeout(
                w.h.conn.createXML, args=("<x/>",), operation_name="libvirt createXML"
            )


def _degraded_writes(degraded):
    return [d for d in degraded if d[1] is True]


class TestHostErrorsDegrade:
    def test_three_read_only_errors_degrade_the_hypervisor(self, env):
        raising, degraded, _ = env
        raising["error"] = _error(VIR_ERR_SYSTEM_ERROR, READ_ONLY)
        w = _worker()

        _call(w, 3)

        assert w.degraded is True
        [(hyp_id, _, reason, source)] = _degraded_writes(degraded)
        assert hyp_id == "hyp-1"
        # only this worker may tell when it is over, not a passing check
        assert source is mod.DEGRADED_BY_HOST_ERRORS
        assert reason.startswith("host error during libvirt createXML")
        assert "Read-only file system" in reason
        message = w.queue_master.get_nowait()
        assert message["type"] == "hyp_degraded"
        assert message["hyp_id"] == "hyp-1"

    def test_two_are_not_enough(self, env):
        raising, degraded, _ = env
        raising["error"] = _error(VIR_ERR_SYSTEM_ERROR, READ_ONLY)
        w = _worker()

        _call(w, 2)

        assert w.degraded is False
        assert _degraded_writes(degraded) == []

    @pytest.mark.parametrize(
        "code, message",
        [
            (VIR_ERR_CONFIG_UNSUPPORTED, IDE),
            (
                VIR_ERR_OPERATION_INVALID,
                "Requested operation is not valid: domain is not running",
            ),
            (
                VIR_ERR_INTERNAL_ERROR,
                "internal error: process exited while connecting to monitor",
            ),
        ],
    )
    def test_domain_errors_never_degrade(self, env, code, message):
        raising, degraded, _ = env
        raising["error"] = _error(code, message)
        w = _worker()

        _call(w, 50)

        assert w.degraded is False
        assert _degraded_writes(degraded) == []

    def test_still_failing_while_degraded_says_so_again(self, env):
        # someone else (the broom, an operator) may have cleared the row
        raising, degraded, _ = env
        raising["error"] = _error(VIR_ERR_SYSTEM_ERROR, READ_ONLY)
        w = _worker()
        _call(w, 3)
        degraded.clear()

        _call(w, 1)

        assert [(h, d, s) for h, d, _, s in degraded] == [
            ("hyp-1", True, mod.DEGRADED_BY_HOST_ERRORS)
        ]


class TestStartDomain:
    def test_the_failing_starts_stay_failed_and_the_host_is_degraded(self, env):
        raising, degraded, statuses = env
        raising["error"] = _error(VIR_ERR_SYSTEM_ERROR, READ_ONLY)
        w = _worker()

        for n in range(3):
            w._handle_start_domain(
                {"type": "start_domain", "id_domain": f"d{n}", "xml": "<x/>"}, 0.0, []
            )

        assert statuses == [("Failed", "d0"), ("Failed", "d1"), ("Failed", "d2")]
        assert w.degraded is True
        assert len(_degraded_writes(degraded)) == 1

    def test_ide_starts_fail_and_the_host_stays_available(self, env):
        raising, degraded, statuses = env
        raising["error"] = _error(VIR_ERR_CONFIG_UNSUPPORTED, IDE)
        w = _worker()

        for n in range(10):
            w._handle_start_domain(
                {"type": "start_domain", "id_domain": f"d{n}", "xml": "<x/>"}, 0.0, []
            )

        assert [s for s, _ in statuses] == ["Failed"] * 10
        assert w.degraded is False
        assert _degraded_writes(degraded) == []
