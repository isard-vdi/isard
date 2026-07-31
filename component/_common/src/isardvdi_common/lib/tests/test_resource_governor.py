"""Unit tests for the Phase-1 resource governor (pure logic).

The governor gates admission of heavy background tasks so they run in low-load
windows and never overload the node — deferring them when the system is under
CPU/IO pressure (Linux PSI) or when heavy concurrency is already at its cap.
"""

import pytest
from isardvdi_common.lib import resource_governor as rg

# --- parse_psi_some_avg10: read /proc/pressure/{cpu,io} "some avg10" ----------


def test_parse_psi_some_avg10_typical():
    text = "some avg10=12.34 avg60=5.00 avg300=1.00 total=123456\n"
    assert rg.parse_psi_some_avg10(text) == pytest.approx(12.34)


def test_parse_psi_some_avg10_full_line_ignored():
    text = (
        "some avg10=3.10 avg60=1.00 avg300=0.50 total=100\n"
        "full avg10=99.00 avg60=50.0 avg300=10.0 total=200\n"
    )
    # must read the 'some' line, not 'full'
    assert rg.parse_psi_some_avg10(text) == pytest.approx(3.10)


def test_parse_psi_some_avg10_missing_returns_zero():
    # a kernel without PSI (no /proc/pressure) -> treat as no pressure
    assert rg.parse_psi_some_avg10("") == 0.0
    assert rg.parse_psi_some_avg10(None) == 0.0


# --- should_defer_heavy: the admission decision ------------------------------


def test_admit_when_idle_and_no_pressure():
    assert (
        rg.should_defer_heavy(
            cpu_psi=1.0, io_psi=2.0, running_heavy=0, psi_limit=40.0, max_heavy=2
        )
        is False
    )


def test_defer_when_cpu_pressure_high():
    assert (
        rg.should_defer_heavy(
            cpu_psi=55.0, io_psi=2.0, running_heavy=0, psi_limit=40.0, max_heavy=2
        )
        is True
    )


def test_defer_when_io_pressure_high():
    assert (
        rg.should_defer_heavy(
            cpu_psi=1.0, io_psi=70.0, running_heavy=0, psi_limit=40.0, max_heavy=2
        )
        is True
    )


def test_defer_when_memory_pressure_high():
    # RAM is the third resource dimension: a convert/sparsify burst that pushes
    # /proc/pressure/memory over the limit must hold heavy admission even when
    # CPU and IO look calm.
    assert (
        rg.should_defer_heavy(
            cpu_psi=1.0,
            io_psi=2.0,
            running_heavy=0,
            psi_limit=40.0,
            max_heavy=2,
            mem_psi=85.0,
        )
        is True
    )


def test_admit_when_memory_below_limit():
    assert (
        rg.should_defer_heavy(
            cpu_psi=1.0,
            io_psi=2.0,
            running_heavy=0,
            psi_limit=40.0,
            max_heavy=2,
            mem_psi=30.0,
        )
        is False
    )


def test_memory_defaults_to_zero_no_defer():
    # Callers that don't pass mem_psi (or a kernel without memory PSI -> 0.0)
    # keep the pre-memory behaviour: no memory-driven deferral.
    assert (
        rg.should_defer_heavy(
            cpu_psi=1.0, io_psi=2.0, running_heavy=0, psi_limit=40.0, max_heavy=2
        )
        is False
    )


def test_defer_when_heavy_concurrency_at_cap():
    # no pressure, but already max_heavy heavy tasks running -> defer (no overload)
    assert (
        rg.should_defer_heavy(
            cpu_psi=1.0, io_psi=1.0, running_heavy=2, psi_limit=40.0, max_heavy=2
        )
        is True
    )


def test_admit_below_cap_and_below_pressure():
    assert (
        rg.should_defer_heavy(
            cpu_psi=30.0, io_psi=30.0, running_heavy=1, psi_limit=40.0, max_heavy=2
        )
        is False
    )


def test_nan_psi_defers_not_admits():
    # A garbage /proc read yielding NaN must DEFER (be conservative),
    # not admit — `nan > limit` is False so a naive comparison would let heavy
    # work through under an unknown pressure state.
    nan = float("nan")
    assert (
        rg.should_defer_heavy(
            cpu_psi=nan, io_psi=1.0, running_heavy=0, psi_limit=40.0, max_heavy=2
        )
        is True
    )
    assert (
        rg.should_defer_heavy(
            cpu_psi=1.0,
            io_psi=2.0,
            mem_psi=nan,
            running_heavy=0,
            psi_limit=40.0,
            max_heavy=2,
        )
        is True
    )


def test_inf_psi_defers():
    assert (
        rg.should_defer_heavy(
            cpu_psi=float("inf"),
            io_psi=1.0,
            running_heavy=0,
            psi_limit=40.0,
            max_heavy=2,
        )
        is True
    )


def test_max_heavy_zero_always_defers():
    assert (
        rg.should_defer_heavy(
            cpu_psi=0.0, io_psi=0.0, running_heavy=0, psi_limit=40.0, max_heavy=0
        )
        is True
    )
