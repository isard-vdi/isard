#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""apiv4 surfaces the qcow2 geometry policy at boot, and never dies for it.

apiv4 is the sole reader of the QCOW2_* vars now, so a distributed install that
set them on the wrong node resolves to the defaults silently. The boot report
logs the resolved policy, warns when the vars are all absent, and -- crucially --
logs (does not raise) a bad policy, so a disk-shape typo cannot crash-loop the
whole API.
"""

import ast
import inspect
import logging
import textwrap

import api
import pytest
from isardvdi_common.helpers import qcow2_geometry

_VARS = (
    "QCOW2_CLUSTER_SIZE",
    "QCOW2_EXTENDED_L2",
    "QCOW2_LAZY_REFCOUNTS",
    "QCOW2_PREALLOCATION",
)


@pytest.fixture(autouse=True)
def _reset_cache():
    qcow2_geometry._cached = None
    yield
    qcow2_geometry._cached = None


def _set(monkeypatch, **vals):
    for var in _VARS:
        monkeypatch.delenv(var, raising=False)
    for var, value in vals.items():
        monkeypatch.setenv(var, value)


def test_valid_policy_logs_it_and_does_not_raise(monkeypatch, caplog):
    _set(
        monkeypatch,
        QCOW2_CLUSTER_SIZE="128k",
        QCOW2_EXTENDED_L2="on",
        QCOW2_LAZY_REFCOUNTS="on",
        QCOW2_PREALLOCATION="off",
    )
    with caplog.at_level(logging.INFO):
        api._report_qcow2_geometry_at_boot()
    assert any("geometry policy resolved" in r.message for r in caplog.records)
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)


def test_all_defaults_is_informational_not_a_warning(monkeypatch, caplog):
    # docker-compose-parts/apiv4.yml supplies the fleet defaults with
    # ${QCOW2_*:-...}, so an install that leaves the keys commented out in its
    # cfg -- which is how isardvdi.cfg.example ships them -- resolves to those
    # defaults by design. That is the normal state and must not warn, or every
    # correctly-configured install logs a warning at every boot.
    _set(monkeypatch)  # nothing set: every key falls back to a default
    with caplog.at_level(logging.INFO):
        api._report_qcow2_geometry_at_boot()
    assert not any(r.levelno >= logging.WARNING for r in caplog.records)
    assert any("compose defaults" in r.message for r in caplog.records)


def test_invalid_policy_logs_error_but_does_not_raise(monkeypatch, caplog):
    # The #5 fix: before, this crashed apiv4 startup and the container
    # crash-looped. It must now log and let the API keep serving.
    _set(monkeypatch, QCOW2_CLUSTER_SIZE="4k", QCOW2_EXTENDED_L2="on")
    with caplog.at_level(logging.ERROR):
        api._report_qcow2_geometry_at_boot()  # must NOT raise
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors, "an invalid policy must be logged at ERROR"
    assert "invalid" in errors[0].message


def test_malformed_min_free_logs_error_but_does_not_raise(monkeypatch, caplog):
    monkeypatch.setenv("STORAGE_MIN_FREE_BYTES", "1G")  # human-readable typo
    with caplog.at_level(logging.ERROR):
        api._validate_storage_min_free_at_boot()  # must NOT raise
    errors = [r for r in caplog.records if r.levelno == logging.ERROR]
    assert errors, "a malformed STORAGE_MIN_FREE_BYTES must be logged at ERROR"
    assert "STORAGE_MIN_FREE_BYTES" in errors[0].message


def test_valid_min_free_is_silent(monkeypatch, caplog):
    monkeypatch.setenv("STORAGE_MIN_FREE_BYTES", "5368709120")
    with caplog.at_level(logging.ERROR):
        api._validate_storage_min_free_at_boot()
    assert not [r for r in caplog.records if r.levelno == logging.ERROR]


def test_lifespan_calls_the_boot_reports():
    """The reports are only useful if the lifespan actually invokes them.
    Parse the AST and look for real Call nodes -- a substring check would pass on
    a commented-out or `if False:`-wrapped call."""
    tree = ast.parse(textwrap.dedent(inspect.getsource(api.lifespan)))
    called = {
        node.func.id
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
    }
    assert "_report_qcow2_geometry_at_boot" in called
    assert "_validate_storage_min_free_at_boot" in called
