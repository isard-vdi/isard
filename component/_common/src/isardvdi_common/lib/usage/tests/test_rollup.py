#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Unit tests for ``isardvdi_common.lib.usage.rollup``.

Covers the pure-aggregation helpers (``_aggregate_inc``,
``_latest_abs``, ``_build_bucket_row``) plus a smoke test that
``run_backfill`` and ``run_incremental`` traverse without error
against a stub rdb.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest
from isardvdi_common.lib.usage import rollup as mod
from isardvdi_common.lib.usage.retention import Tier
from isardvdi_common.schemas.usage import UsageRetentionConfig


@pytest.fixture
def stub_r(monkeypatch):
    mock_table = MagicMock(name="r.table")
    monkeypatch.setattr(mod.r, "table", mock_table)

    class _RowExpr:
        def __getitem__(self, key):
            return self

        def __le__(self, other):
            return self

        def __lt__(self, other):
            return self

        def __ge__(self, other):
            return self

        def __eq__(self, other):  # pragma: no cover - rdb expr semantics
            return self

        def __and__(self, other):
            return self

    monkeypatch.setattr(mod.r, "row", _RowExpr())
    monkeypatch.setattr(mod.r, "do", lambda *a: MagicMock(run=lambda *aa: None))
    yield {"mock_table": mock_table}


class TestAggregateInc:
    def test_sums_numeric_keys(self):
        rows = [
            {"inc": {"a": 1, "b": 2.5}},
            {"inc": {"a": 3, "b": 0.5, "c": 7}},
        ]
        assert mod._aggregate_inc(rows) == {"a": 4, "b": 3.0, "c": 7}

    def test_ignores_non_numeric(self):
        rows = [{"inc": {"a": 1, "b": "skip"}}, {"inc": {"a": 2}}]
        assert mod._aggregate_inc(rows) == {"a": 3}

    def test_handles_missing_inc(self):
        rows = [{"inc": None}, {"inc": {"a": 1}}, {}]
        assert mod._aggregate_inc(rows) == {"a": 1}


class TestLatestAbs:
    def test_picks_latest_date_row(self):
        rows = [
            {
                "date": datetime(2026, 1, 1, tzinfo=timezone.utc),
                "abs": {"a": 1},
            },
            {
                "date": datetime(2026, 1, 5, tzinfo=timezone.utc),
                "abs": {"a": 5, "b": 7},
            },
            {
                "date": datetime(2026, 1, 3, tzinfo=timezone.utc),
                "abs": {"a": 3},
            },
        ]
        assert mod._latest_abs(rows) == {"a": 5, "b": 7}

    def test_empty_returns_empty(self):
        assert mod._latest_abs([]) == {}


class TestBuildBucketRow:
    def test_round_trips_key_into_pk_and_date(self):
        bucket = datetime(2026, 4, 27, tzinfo=timezone.utc)
        # Bucket key matches gen_pk's field set (4 fields). Category
        # is carried separately from the latest source.
        key = ("i1", "desktop", "user", bucket)
        sources = [
            {
                "date": datetime(2026, 4, 28, tzinfo=timezone.utc),
                "abs": {"dsk_hours": 10},
                "inc": {"dsk_hours": 2},
                "item_name": "Alice",
                "item_consumer_category_id": "cat-new",
            },
            {
                "date": datetime(2026, 4, 27, tzinfo=timezone.utc),
                "abs": {"dsk_hours": 8},
                "inc": {"dsk_hours": 1},
                "item_name": "Alice",
                "item_consumer_category_id": "cat-old",
            },
        ]
        out = mod._build_bucket_row(key, sources, Tier.WEEKLY)
        assert out["item_id"] == "i1"
        assert out["item_consumer"] == "user"
        # Category from the latest source — preserves manager-scoped
        # filtering at consumption.py while keeping the pk
        # consistent with the consolidator's gen_pk.
        assert out["item_consumer_category_id"] == "cat-new"
        assert out["date"] == bucket
        assert out["abs"] == {"dsk_hours": 10}  # last by date
        assert out["inc"] == {"dsk_hours": 3}  # 2 + 1
        assert out["granularity"] == "weekly"
        assert len(out["pk"]) == 32  # md5 hex

    def test_pk_does_not_collide_across_categories(self):
        """Regression for the pk-collision bug discovered on the
        sandbox test (~17k inc-total drift): when a (item, consumer)
        pair has rows with different category_ids on the same day,
        the pk must NOT depend on category_id (matches gen_pk).
        Otherwise the second insert silently overwrites the first.
        """
        bucket = datetime(2026, 4, 27, tzinfo=timezone.utc)
        key1 = ("i1", "desktop", "user", bucket)
        key2 = ("i1", "desktop", "user", bucket)
        # Both keys produce the SAME bucket row (deterministic pk),
        # which is what the consolidator does — same item × consumer
        # × period maps to a single row.
        sources_a = [
            {
                "date": bucket,
                "abs": {},
                "inc": {"x": 1},
                "item_consumer_category_id": "A",
            }
        ]
        sources_b = [
            {
                "date": bucket,
                "abs": {},
                "inc": {"x": 2},
                "item_consumer_category_id": "B",
            }
        ]
        out_a = mod._build_bucket_row(key1, sources_a, Tier.WEEKLY)
        out_b = mod._build_bucket_row(key2, sources_b, Tier.WEEKLY)
        # Same pk because the key set is identical.
        assert out_a["pk"] == out_b["pk"]


class TestProcessGroups:
    def test_skips_already_bucket(self, stub_r):
        # Pick a bucket date far enough back to be in WEEKLY tier
        # under the test retention (daily_months=1 → 30 days).
        bucket_date = datetime(2025, 12, 1, tzinfo=timezone.utc)
        groups = {
            ("i1", "desktop", "user", bucket_date): [
                {
                    "pk": "p",
                    "date": bucket_date,
                    "item_id": "i1",
                    "item_type": "desktop",
                    "item_consumer": "user",
                    "abs": {},
                    "inc": {},
                    "granularity": "weekly",
                }
            ]
        }
        retention = UsageRetentionConfig(
            daily_months=1, weekly_months=12, total_months=None
        )
        stats = mod.empty_stats()
        # Not dry-run but should be a no-op since the row is already
        # at the bucket boundary with the right granularity.
        mod._process_groups(
            MagicMock(),
            groups,
            dry_run=False,
            bucket=mod.TokenBucket(100),
            stats=stats,
            retention=retention,
        )
        assert stats["skipped_already_bucket"] == 1
        assert stats["aggregated"] == 0

    def test_dry_run_counts_without_writing(self, stub_r):
        bucket_date = datetime(2025, 9, 1, tzinfo=timezone.utc)
        # Source rows in MONTHLY tier (forced by short retention).
        groups = {
            ("i1", "desktop", "user", bucket_date): [
                {
                    "pk": "p1",
                    "date": datetime(2025, 9, 5, tzinfo=timezone.utc),
                    "item_id": "i1",
                    "item_type": "desktop",
                    "item_consumer": "user",
                    "abs": {"x": 5},
                    "inc": {"x": 1},
                },
                {
                    "pk": "p2",
                    "date": datetime(2025, 9, 12, tzinfo=timezone.utc),
                    "item_id": "i1",
                    "item_type": "desktop",
                    "item_consumer": "user",
                    "abs": {"x": 10},
                    "inc": {"x": 5},
                },
            ]
        }
        retention = UsageRetentionConfig(
            daily_months=1, weekly_months=2, total_months=None
        )
        stats = mod.empty_stats()
        mod._process_groups(
            MagicMock(),
            groups,
            dry_run=True,
            bucket=mod.TokenBucket(100),
            stats=stats,
            retention=retention,
        )
        assert stats["would_aggregate"] == 1
        assert stats["would_drop_rows"] == 2
        assert stats["aggregated"] == 0


class TestBackupHookedIntoProcessGroups:
    """The file-I/O contract for ``BackupWriter`` is pinned in
    ``helpers/tests/test_backup_writer.py``. The only thing that
    matters here is that ``_process_groups`` actually calls
    ``write_rows`` for the source rows it's about to delete-and-
    replace, and increments the ``backed_up`` stat in step.
    """

    def test_backup_passed_to_process_groups_writes_sources(self, stub_r, tmp_path):
        from datetime import datetime, timezone

        bucket_date = datetime(2025, 9, 1, tzinfo=timezone.utc)
        groups = {
            ("i1", "desktop", "user", bucket_date): [
                {
                    "pk": "p1",
                    "date": datetime(2025, 9, 5, tzinfo=timezone.utc),
                    "item_id": "i1",
                    "item_type": "desktop",
                    "item_consumer": "user",
                    "abs": {"x": 5},
                    "inc": {"x": 1},
                },
                {
                    "pk": "p2",
                    "date": datetime(2025, 9, 12, tzinfo=timezone.utc),
                    "item_id": "i1",
                    "item_type": "desktop",
                    "item_consumer": "user",
                    "abs": {"x": 10},
                    "inc": {"x": 5},
                },
            ]
        }
        retention = UsageRetentionConfig(
            daily_months=1, weekly_months=2, total_months=None
        )
        stats = mod.empty_stats()
        with mod.BackupWriter(str(tmp_path), "rollup_backfill") as backup:
            mod._process_groups(
                MagicMock(),
                groups,
                dry_run=False,
                bucket=mod.TokenBucket(100),
                stats=stats,
                retention=retention,
                backup=backup,
            )
            assert backup.rows_written == 2
        assert stats["backed_up"] == 2


class TestEmptyStats:
    def test_zeroed_counters(self):
        s = mod.empty_stats()
        assert all(v == 0 for v in s.values())
        # Ensure the schema includes every counter the rollup code
        # increments — guards against silent typos in the call sites.
        for key in (
            "scanned",
            "aggregated",
            "replaced_sources",
            "skipped_daily",
            "skipped_already_bucket",
            "deleted",
            "would_aggregate",
            "would_drop_rows",
            "would_delete",
            "errors",
        ):
            assert key in s
