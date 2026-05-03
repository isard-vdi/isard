#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``isardvdi_common.lib.usage.retention``.

Pins:

* classify_tier respects the daily/weekly/monthly boundaries against
  a fixed ``now`` for determinism.
* bucket_for rounds dates to Monday-of-week / first-of-month UTC.
* bucket_pk is deterministic and matches the consolidator's md5
  scheme so re-runs land on the same row.
* load_config falls back to schema defaults when the field is absent.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from isardvdi_common.lib.usage import retention as mod
from isardvdi_common.schemas.usage import UsageRetentionConfig


class TestAssertTierOrdering:
    def test_default_passes(self):
        UsageRetentionConfig().assert_tier_ordering()

    def test_inverted_daily_weekly_raises(self):
        cfg = UsageRetentionConfig(daily_months=6, weekly_months=3)
        with pytest.raises(ValueError, match="weekly_months"):
            cfg.assert_tier_ordering()

    def test_total_below_weekly_raises(self):
        cfg = UsageRetentionConfig(daily_months=2, weekly_months=6, total_months=4)
        with pytest.raises(ValueError, match="total_months"):
            cfg.assert_tier_ordering()

    def test_total_unset_skips_check(self):
        UsageRetentionConfig(
            daily_months=1, weekly_months=2, total_months=None
        ).assert_tier_ordering()


_NOW = datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)
_DEFAULT = UsageRetentionConfig()


class TestClassifyTier:
    def test_today_is_daily(self):
        assert mod.classify_tier(_NOW, _DEFAULT, now=_NOW) is mod.Tier.DAILY

    def test_one_month_old_is_daily(self):
        d = datetime(2026, 4, 1, tzinfo=timezone.utc)  # 32 days old
        assert mod.classify_tier(d, _DEFAULT, now=_NOW) is mod.Tier.DAILY

    def test_just_over_daily_threshold_is_weekly(self):
        # daily_months=3 → 90 days. 95 days back → weekly.
        d = _NOW.replace(year=2026, month=1, day=28)  # 95 days back
        assert mod.classify_tier(d, _DEFAULT, now=_NOW) is mod.Tier.WEEKLY

    def test_over_weekly_threshold_is_monthly(self):
        # weekly_months=6 → 180 days. 200 days back → monthly.
        d = _NOW.replace(year=2025, month=10, day=15)
        assert mod.classify_tier(d, _DEFAULT, now=_NOW) is mod.Tier.MONTHLY

    def test_over_total_months_is_delete(self):
        capped = UsageRetentionConfig(daily_months=3, weekly_months=6, total_months=12)
        d = _NOW.replace(year=2024, month=1, day=15)  # ~16 months back
        assert mod.classify_tier(d, capped, now=_NOW) is mod.Tier.DELETE

    def test_total_months_unset_keeps_history(self):
        d = datetime(2010, 1, 1, tzinfo=timezone.utc)
        # default has total_months=None → never DELETE.
        assert mod.classify_tier(d, _DEFAULT, now=_NOW) is mod.Tier.MONTHLY


class TestBucketFor:
    def test_daily_returns_midnight_utc(self):
        d = datetime(2026, 5, 3, 12, 34, 56, 789, tzinfo=timezone.utc)
        assert mod.bucket_for(d, mod.Tier.DAILY) == datetime(
            2026, 5, 3, tzinfo=timezone.utc
        )

    def test_weekly_returns_monday_of_iso_week(self):
        # Sunday 2026-05-03 → Monday 2026-04-27.
        d = datetime(2026, 5, 3, 12, 0, tzinfo=timezone.utc)
        assert mod.bucket_for(d, mod.Tier.WEEKLY) == datetime(
            2026, 4, 27, tzinfo=timezone.utc
        )

    def test_weekly_on_monday_is_idempotent(self):
        d = datetime(2026, 4, 27, 23, 59, tzinfo=timezone.utc)
        assert mod.bucket_for(d, mod.Tier.WEEKLY) == datetime(
            2026, 4, 27, tzinfo=timezone.utc
        )

    def test_monthly_returns_first_of_month(self):
        d = datetime(2026, 5, 31, 23, 59, tzinfo=timezone.utc)
        assert mod.bucket_for(d, mod.Tier.MONTHLY) == datetime(
            2026, 5, 1, tzinfo=timezone.utc
        )

    def test_delete_tier_has_no_bucket(self):
        d = datetime(2024, 1, 1, tzinfo=timezone.utc)
        with pytest.raises(ValueError):
            mod.bucket_for(d, mod.Tier.DELETE)


class TestBucketPk:
    def test_deterministic_across_calls(self):
        bucket = datetime(2026, 5, 1, tzinfo=timezone.utc)
        a = mod.bucket_pk("item-1", "desktop", "user", bucket)
        b = mod.bucket_pk("item-1", "desktop", "user", bucket)
        assert a == b

    def test_changes_with_any_field(self):
        bucket = datetime(2026, 5, 1, tzinfo=timezone.utc)
        base = mod.bucket_pk("item-1", "desktop", "user", bucket)
        assert mod.bucket_pk("item-2", "desktop", "user", bucket) != base
        assert mod.bucket_pk("item-1", "media", "user", bucket) != base
        assert mod.bucket_pk("item-1", "desktop", "group", bucket) != base
        assert (
            mod.bucket_pk(
                "item-1",
                "desktop",
                "user",
                datetime(2026, 5, 8, tzinfo=timezone.utc),
            )
            != base
        )

    def test_md5_hex_format(self):
        bucket = datetime(2026, 5, 1, tzinfo=timezone.utc)
        pk = mod.bucket_pk("item-1", "desktop", "user", bucket)
        assert len(pk) == 32 and all(c in "0123456789abcdef" for c in pk)


class TestLoadConfig:
    def test_returns_defaults_when_field_absent(self, monkeypatch):
        conn = MagicMock(name="conn")
        # Stub the rdb chain: r.table().get().pluck().default().run() → {}.
        chain = MagicMock()
        chain.run.return_value = {}
        monkeypatch.setattr(mod.r, "table", lambda *a, **kw: chain)
        for method in ("get", "pluck", "default"):
            setattr(chain, method, lambda *a, **kw: chain)
        cfg = mod.load_config(conn)
        assert isinstance(cfg, UsageRetentionConfig)
        assert cfg.daily_months == 3 and cfg.weekly_months == 6
        assert cfg.total_months is None

    def test_returns_stored_values(self, monkeypatch):
        conn = MagicMock(name="conn")
        chain = MagicMock()
        chain.run.return_value = {
            "usage_retention": {
                "daily_months": 1,
                "weekly_months": 4,
                "total_months": 24,
            }
        }
        monkeypatch.setattr(mod.r, "table", lambda *a, **kw: chain)
        for method in ("get", "pluck", "default"):
            setattr(chain, method, lambda *a, **kw: chain)
        cfg = mod.load_config(conn)
        assert cfg.daily_months == 1
        assert cfg.weekly_months == 4
        assert cfg.total_months == 24
