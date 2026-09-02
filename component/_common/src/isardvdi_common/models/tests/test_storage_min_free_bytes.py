#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""``STORAGE_MIN_FREE_BYTES`` is an installation policy resolved by the enqueuer.

It is now documented in isardvdi.cfg.example for the first time, so operators
will set it -- and the geometry vars two lines above it are human-readable
(``4k``/``2M``), which invites a ``1G`` typo. A bare ``int()`` would raise only
at enqueue time, AFTER the row is flipped to maintenance. These pin that the
value is validated up front and carried in the disconnect/convert payload.
"""

import pytest
from isardvdi_common.models.storage import storage_min_free_bytes


def test_absent_falls_back_to_one_gib(monkeypatch):
    monkeypatch.delenv("STORAGE_MIN_FREE_BYTES", raising=False)
    assert storage_min_free_bytes() == 1 << 30


def test_empty_falls_back_to_one_gib(monkeypatch):
    monkeypatch.setenv("STORAGE_MIN_FREE_BYTES", "")
    assert storage_min_free_bytes() == 1 << 30


def test_a_valid_integer_is_used(monkeypatch):
    monkeypatch.setenv("STORAGE_MIN_FREE_BYTES", "5368709120")
    assert storage_min_free_bytes() == 5368709120


def test_a_human_readable_value_is_rejected(monkeypatch):
    monkeypatch.setenv("STORAGE_MIN_FREE_BYTES", "1G")
    with pytest.raises(ValueError, match="STORAGE_MIN_FREE_BYTES"):
        storage_min_free_bytes()


def test_a_negative_value_is_rejected(monkeypatch):
    monkeypatch.setenv("STORAGE_MIN_FREE_BYTES", "-1")
    with pytest.raises(ValueError, match="must be >= 0"):
        storage_min_free_bytes()
