#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tests for the bounded retry in ``helpers.scheduler._post_advanced_date``.

A single timeout used to permanently drop the registration of a booking-end
date job during a scheduler burst. ``_post_advanced_date`` now retries a
small, FINITE number of times with a short backoff, while staying
fire-and-forget (it never raises to the caller and never loops forever).
"""

import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def patched(monkeypatch):
    from isardvdi_common.helpers import scheduler as mod

    # Don't build a real body or client / don't actually sleep.
    # MagicMock natively supports the ``with`` context-manager protocol.
    monkeypatch.setattr(mod, "_build_advanced_date_body", lambda data: {"ok": True})
    monkeypatch.setattr(mod, "_build_scheduler_client", lambda: MagicMock())
    monkeypatch.setattr("time.sleep", lambda *_: None)

    calls = {"n": 0}

    def install_post(behaviour):
        def sync_detailed(**kwargs):
            calls["n"] += 1
            return behaviour(calls["n"])

        fake = types.ModuleType("isardvdi_scheduler_client.api.jobs")
        fake.post_scheduler_advanced_date = SimpleNamespace(sync_detailed=sync_detailed)
        monkeypatch.setitem(sys.modules, "isardvdi_scheduler_client.api.jobs", fake)

    return mod, calls, install_post


def test_retries_are_finite_and_dont_raise(patched, caplog):
    mod, calls, install_post = patched

    def always_raise(_n):
        raise RuntimeError("scheduler down")

    install_post(always_raise)
    # Must not raise to the caller (fire-and-forget).
    mod._post_advanced_date("desktop", "desktop_notify", {})
    assert calls["n"] == mod._SCHEDULER_POST_ATTEMPTS  # bounded, finite
    assert mod._SCHEDULER_POST_ATTEMPTS <= 5  # guard: never "forever"
    assert "could not contact scheduler service" in caplog.text


def test_succeeds_after_a_transient_failure(patched, caplog):
    mod, calls, install_post = patched

    def fail_once_then_ok(n):
        if n < 2:
            raise RuntimeError("transient stall")
        return SimpleNamespace(status_code=200)

    install_post(fail_once_then_ok)
    mod._post_advanced_date("bookings", "domain_reservable_set", {})
    assert calls["n"] == 2  # stopped as soon as it succeeded
    assert "could not contact scheduler service" not in caplog.text


def test_non_2xx_status_is_retried(patched):
    mod, calls, install_post = patched

    def server_error(_n):
        return SimpleNamespace(status_code=503)

    install_post(server_error)
    mod._post_advanced_date("desktop", "desktop_notify", {})
    assert calls["n"] == mod._SCHEDULER_POST_ATTEMPTS
