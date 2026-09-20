# SPDX-License-Identifier: AGPL-3.0-or-later

"""Free-space floor: refuse/pause a migration whose destination is too full.

A percentage floor on the destination's physical space, coexisting with the
absolute byte floor — the most restrictive wins. An unknown reading never
breaches (fail open: the per-move worker floor is the backstop). The runner tick
pause and the apiv4 start gate are exercised in test_migration_recurring_drive
and test_admin_storage_migration; here are the pure decisions.
"""

from isardvdi_common.lib.storage import migration as mig


def test_free_pct_basic():
    assert mig.free_pct(50, 100) == 50.0
    assert mig.free_pct(1, 4) == 25.0


def test_free_pct_unknown_is_none():
    assert mig.free_pct(50, 0) is None
    assert mig.free_pct(50, None) is None
    assert mig.free_pct(None, 100) is None


def test_free_pct_clamped():
    assert mig.free_pct(150, 100) == 100.0
    assert mig.free_pct(-5, 100) == 0.0


def test_pct_floor_breached_below():
    assert mig.space_floor_breached(5, 100, 10) is True  # 5% < 10%


def test_pct_floor_ok_above():
    assert mig.space_floor_breached(50, 100, 10) is False


def test_pct_floor_disabled_by_zero():
    assert mig.space_floor_breached(1, 100, 0) is False


def test_byte_floor_breached():
    assert mig.space_floor_breached(500, 10**9, 0, min_free_bytes=1000) is True


def test_byte_floor_ok():
    assert mig.space_floor_breached(2000, 10**9, 0, min_free_bytes=1000) is False


def test_most_restrictive_wins_bytes_over_pct():
    # 50% free clears the 10% pct floor, but 50 GiB is below a 100 GiB byte floor
    assert (
        mig.space_floor_breached(
            50 * 10**9, 100 * 10**9, 10, min_free_bytes=100 * 10**9
        )
        is True
    )


def test_most_restrictive_wins_pct_over_bytes():
    # 5 GiB clears a 1 GiB byte floor, but 5% is below the 10% pct floor
    assert (
        mig.space_floor_breached(5 * 10**9, 100 * 10**9, 10, min_free_bytes=10**9)
        is True
    )


def test_both_floors_satisfied():
    assert (
        mig.space_floor_breached(50 * 10**9, 100 * 10**9, 10, min_free_bytes=10**9)
        is False
    )


def test_unknown_reading_never_breaches():
    assert mig.space_floor_breached(None, 100, 90) is False
    assert mig.space_floor_breached(None, None, 90, min_free_bytes=10**12) is False
