#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for ``job_timeout_for`` — the per-action RQ job_timeout budget.

Storage tasks enqueued without an explicit timeout used to inherit RQ's
180 s ``Queue.DEFAULT_TIMEOUT``, which killed any long-running operation (a
multi-GB download / convert / sparsify / move) mid-flight. ``job_timeout_for``
gives fast tasks a small ceiling and long tasks a size-derived (or CEIL)
budget so they run to completion.
"""

import importlib

import isardvdi_common.helpers.task_timeouts as tt


def test_fast_action_gets_fast_timeout():
    assert tt.job_timeout_for("delete") == tt.FAST_TIMEOUT
    assert tt.job_timeout_for("update_status") == tt.FAST_TIMEOUT
    assert tt.job_timeout_for("qemu_img_info_backing_chain") == tt.FAST_TIMEOUT


def test_unknown_action_gets_fast_timeout():
    assert tt.job_timeout_for("some_future_task") == tt.FAST_TIMEOUT
    assert tt.job_timeout_for(None) == tt.FAST_TIMEOUT


def test_long_action_without_size_gets_ceil():
    for action in ("download_url", "convert", "sparsify", "move", "create"):
        assert tt.job_timeout_for(action) == tt.LONG_CEIL


def test_long_action_size_is_clamped():
    # A tiny disk is floored (never below the FLOOR).
    assert tt.job_timeout_for("convert", size_bytes=1) == tt.LONG_FLOOR
    # A huge disk is capped at the CEIL.
    huge = tt.MIN_THROUGHPUT_BPS * (tt.LONG_CEIL + 10_000)
    assert tt.job_timeout_for("move", size_bytes=huge) == tt.LONG_CEIL


def test_long_action_mid_size_is_derived():
    # Pick a size whose derived budget lands strictly inside [FLOOR, CEIL].
    seconds = (tt.LONG_FLOOR + tt.LONG_CEIL) // 2
    size = seconds * tt.MIN_THROUGHPUT_BPS
    assert tt.job_timeout_for("download_url", size_bytes=size) == seconds


def test_zero_or_negative_size_falls_back_to_ceil():
    assert tt.job_timeout_for("sparsify", size_bytes=0) == tt.LONG_CEIL
    assert tt.job_timeout_for("sparsify", size_bytes=-5) == tt.LONG_CEIL


def test_env_overrides_are_honoured(monkeypatch):
    monkeypatch.setenv("STORAGE_TASK_FAST_TIMEOUT", "42")
    monkeypatch.setenv("STORAGE_TASK_TIMEOUT_CEIL", "999")
    monkeypatch.setenv("STORAGE_TASK_TIMEOUT_FLOOR", "100")
    reloaded = importlib.reload(tt)
    try:
        assert reloaded.job_timeout_for("delete") == 42
        assert reloaded.job_timeout_for("download_url") == 999
        assert reloaded.job_timeout_for("convert", size_bytes=1) == 100
    finally:
        # Restore module-level constants for the rest of the suite.
        monkeypatch.undo()
        importlib.reload(tt)


def test_invalid_env_is_ignored(monkeypatch):
    monkeypatch.setenv("STORAGE_TASK_FAST_TIMEOUT", "not-a-number")
    monkeypatch.setenv("STORAGE_TASK_TIMEOUT_CEIL", "-1")
    reloaded = importlib.reload(tt)
    try:
        assert reloaded.job_timeout_for("delete") == 300  # default kept
        assert reloaded.job_timeout_for("convert") == 6 * 3600  # default kept
    finally:
        monkeypatch.undo()
        importlib.reload(tt)
