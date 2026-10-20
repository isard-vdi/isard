"""Which libvirt errors are the host's own system failing, and how they count."""

import pytest
from libvirt import (
    VIR_ERR_CONFIG_UNSUPPORTED,
    VIR_ERR_INTERNAL_ERROR,
    VIR_ERR_OPERATION_INVALID,
    VIR_ERR_SYSTEM_ERROR,
    libvirtError,
)

from engine.services.lib import libvirt_timeout as mod

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


class TestIsHostError:
    @pytest.mark.parametrize(
        "message",
        [
            READ_ONLY,
            "Failed to write file '/run/libvirt/x': No space left on device",
            "cannot open file '/var/lib/libvirt/x': Input/output error",
            "unable to stat '/var/lib/libvirt/x': Structure needs cleaning",
        ],
    )
    def test_a_system_error_on_the_host_filesystem_is_a_host_error(self, message):
        assert mod.is_host_error(_error(VIR_ERR_SYSTEM_ERROR, message))

    def test_the_local_code_matches_libvirt(self):
        assert mod.VIR_ERR_SYSTEM_ERROR == VIR_ERR_SYSTEM_ERROR

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
    def test_domain_errors_are_not_host_errors(self, code, message):
        assert not mod.is_host_error(_error(code, message))

    def test_the_errno_text_alone_is_not_enough(self):
        # qemu failing on the desktop's disk says the same words, but it is
        # the domain's storage, not libvirtd failing on the host
        message = f"internal error: qemu unexpectedly closed: {READ_ONLY}"
        assert not mod.is_host_error(_error(VIR_ERR_INTERNAL_ERROR, message))

    def test_another_system_error_is_not_a_host_error(self):
        message = "Cannot access storage file '/isard/x.qcow2': No such file"
        assert not mod.is_host_error(_error(VIR_ERR_SYSTEM_ERROR, message))

    def test_a_timeout_or_a_plain_exception_is_not_a_host_error(self):
        assert not mod.is_host_error(mod.LibvirtTimeoutError("createXML", 30, "h"))
        assert not mod.is_host_error(RuntimeError(READ_ONLY))


class TestHostErrorCount:
    @pytest.fixture
    def clock(self, monkeypatch):
        now = {"t": 1000.0}
        monkeypatch.setattr(mod.time, "time", lambda: now["t"])
        return now

    def test_the_threshold_within_the_window_degrades(self, clock):
        stats = mod.LibvirtOperationStats("hyp-1")
        for _ in range(mod.HOST_ERROR_THRESHOLD - 1):
            stats.record_host_error()
            clock["t"] += 10
        assert not stats.should_degrade()
        stats.record_host_error()
        assert stats.should_degrade()

    def test_errors_older_than_the_window_are_forgotten(self, clock):
        stats = mod.LibvirtOperationStats("hyp-1")
        for _ in range(mod.HOST_ERROR_THRESHOLD):
            stats.record_host_error()
            clock["t"] += mod.HOST_ERROR_WINDOW_SECONDS / 2 + 1
        assert not stats.should_degrade()

    def test_a_host_error_restarts_the_count_towards_recovery(self, clock):
        stats = mod.LibvirtOperationStats("hyp-1")
        for _ in range(mod.RECOVERY_WINDOW):
            stats.record_response(5)
        stats.record_host_error()
        assert stats.normal_response_count == 0
        assert not stats.should_recover(clock["t"] - mod.DEGRADED_RECOVERY_SECONDS)

    def test_reset_forgets_the_host_errors(self, clock):
        stats = mod.LibvirtOperationStats("hyp-1")
        for _ in range(mod.HOST_ERROR_THRESHOLD):
            stats.record_host_error()
        stats.reset()
        assert not stats.should_degrade()
