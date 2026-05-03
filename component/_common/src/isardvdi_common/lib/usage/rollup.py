#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Tiered rollup logic for ``usage_consumption``.

Library entry points used by both the offline CLI script
(``engine/scripts/rollup_usage_consumption.py``) and the apiv4 daily
consolidator chain (``AdminUsageService.consolidate_consumptions``).

Two modes:

* :func:`run_backfill` — walks every row outside the safety margin.
* :func:`run_incremental` — walks only the tier-transition windows.

Both modes share :func:`_process_groups` for the per-bucket
aggregate-and-replace step. The 7-day safety margin guarantees we
never collide with the day-N or day-N-1 consolidation that may still
be running with ``conflict='update'``.
"""

import gzip
import json
import logging
import os
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Optional, TextIO

from isardvdi_common.lib.usage.retention import (
    Tier,
    bucket_for,
    bucket_pk,
    classify_tier,
)
from isardvdi_common.schemas.usage import UsageRetentionConfig
from rethinkdb import r

log = logging.getLogger(__name__)

SAFETY_MARGIN_DAYS = 7
INCREMENTAL_WINDOW_DAYS = 7  # ± around each tier boundary


def _json_default(value):
    """JSON serializer for ``datetime`` (and any other awkward types)."""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


class BackupWriter:
    """Streams source rows to a gzipped JSONL file before deletion.

    One file per rollup run, keyed by ISO timestamp + mode. Gzip is
    streaming so memory stays bounded regardless of total volume.
    A single ``.jsonl.gz`` file is the cleanest container for a single
    output stream — tar.gz only buys anything when there are many
    files, and we deliberately stay one-file-per-run.

    The writer is a context manager so the caller can guarantee the
    file is closed (and gzip footer flushed) on the way out.
    """

    def __init__(self, backup_dir: str, mode: str):
        self.backup_dir = backup_dir
        os.makedirs(backup_dir, exist_ok=True)
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self.path = os.path.join(
            backup_dir, f"usage_consumption_rollup_{ts}_{mode}.jsonl.gz"
        )
        self._fh: Optional[TextIO] = None
        self.rows_written = 0
        self.bytes_written = 0

    def __enter__(self) -> "BackupWriter":
        self._fh = gzip.open(self.path, "wt", encoding="utf-8")
        log.info("rollup backup → %s", self.path)
        return self

    def __exit__(self, *exc):
        if self._fh is not None:
            self._fh.close()
            self._fh = None
        if self.rows_written:
            try:
                self.bytes_written = os.path.getsize(self.path)
            except OSError:
                self.bytes_written = -1
            log.info(
                "rollup backup closed: %d rows, %.1f KB compressed",
                self.rows_written,
                self.bytes_written / 1024,
            )
        return False

    def write_rows(self, rows) -> None:
        if self._fh is None:
            return
        for row in rows:
            line = json.dumps(row, default=_json_default, ensure_ascii=False)
            self._fh.write(line + "\n")
            self.rows_written += 1


def empty_stats() -> dict:
    return {
        "scanned": 0,
        "aggregated": 0,
        "replaced_sources": 0,
        "skipped_daily": 0,
        "skipped_already_bucket": 0,
        "deleted": 0,
        "backed_up": 0,
        "would_aggregate": 0,
        "would_drop_rows": 0,
        "would_delete": 0,
        "errors": 0,
    }


class TokenBucket:
    """qps-limited single-thread token bucket."""

    def __init__(self, qps: int):
        self.rate = max(1, qps)
        self.capacity = float(self.rate)
        self.tokens = float(self.rate)
        self.last = time.monotonic()

    def take(self) -> None:
        now = time.monotonic()
        elapsed = now - self.last
        self.last = now
        self.tokens = min(self.capacity, self.tokens + elapsed * self.rate)
        if self.tokens < 1.0:
            time.sleep((1.0 - self.tokens) / self.rate)
            self.tokens = 0.0
        else:
            self.tokens -= 1.0


def _safety_cutoff(now: datetime) -> datetime:
    return now - timedelta(days=SAFETY_MARGIN_DAYS)


def _aggregate_inc(rows: list[dict]) -> dict:
    out: dict = defaultdict(float)
    for row in rows:
        for key, val in (row.get("inc") or {}).items():
            if isinstance(val, (int, float)):
                out[key] += val
    return dict(out)


def _latest_abs(rows: list[dict]) -> dict:
    if not rows:
        return {}
    latest = max(rows, key=lambda x: x["date"])
    return dict(latest.get("abs") or {})


def _bucket_key(row: dict, tier: Tier) -> tuple:
    """Group key for the rollup.

    Mirrors the consolidator's ``gen_pk`` field set: ``item_id``,
    ``item_type``, ``item_consumer``, plus the bucket boundary in
    place of the consolidation day. ``item_consumer_category_id``
    is intentionally NOT part of the key — including it splits a
    single (item, consumer) pair into multiple groups, but
    ``bucket_pk`` only hashes 4 fields, so the resulting bucket rows
    collide on pk and the second insert silently overwrites the
    first. Aligning the key with ``gen_pk`` keeps category_id
    derivation deterministic (carried from the latest source) and
    avoids pk collisions / data loss.
    """
    return (
        row["item_id"],
        row["item_type"],
        row["item_consumer"],
        bucket_for(row["date"], tier),
    )


def _build_bucket_row(key: tuple, sources: list[dict], tier: Tier) -> dict:
    item_id, item_type, item_consumer, bucket_date = key
    latest = max(sources, key=lambda s: s["date"])
    return {
        "pk": bucket_pk(item_id, item_type, item_consumer, bucket_date),
        "date": bucket_date,
        "item_id": item_id,
        "item_type": item_type,
        "item_consumer": item_consumer,
        # Carry category_id from the most recent source so the
        # manager-scoped filtering at consumption.py:111-114 keeps
        # working. Within a (item, consumer) bucket the category
        # rarely changes, but if it did the latest one wins.
        "item_consumer_category_id": latest.get("item_consumer_category_id"),
        "item_name": latest.get("item_name"),
        "abs": _latest_abs(sources),
        "inc": _aggregate_inc(sources),
        "granularity": tier.value,
    }


def _process_groups(
    conn,
    groups: dict,
    *,
    dry_run: bool,
    bucket: TokenBucket,
    stats: dict,
    retention: UsageRetentionConfig,
    backup: Optional[BackupWriter] = None,
) -> None:
    for key, sources in groups.items():
        if not sources:
            continue
        tier = classify_tier(sources[0]["date"], retention)
        if tier is Tier.DAILY:
            stats["skipped_daily"] += 1
            continue
        if tier is Tier.DELETE:
            if dry_run:
                stats["would_delete"] += len(sources)
                continue
            if backup is not None:
                backup.write_rows(sources)
                stats["backed_up"] += len(sources)
            bucket.take()
            r.table("usage_consumption").get_all(*[s["pk"] for s in sources]).delete(
                durability="hard"
            ).run(conn)
            stats["deleted"] += len(sources)
            continue

        bucket_date = key[-1]
        if (
            len(sources) == 1
            and sources[0]["date"] == bucket_date
            and sources[0].get("granularity") == tier.value
        ):
            stats["skipped_already_bucket"] += 1
            continue

        new_row = _build_bucket_row(key, sources, tier)
        if dry_run:
            stats["would_aggregate"] += 1
            stats["would_drop_rows"] += len(sources)
            continue

        # Backup BEFORE the destructive r.do — if the file write fails,
        # we never delete, and an admin can re-run after fixing the
        # backup target. If the rdb update fails after the backup
        # write, the backup row is still valid (it's the original
        # source).
        if backup is not None:
            backup.write_rows(sources)
            stats["backed_up"] += len(sources)

        # When a source row already sits at the bucket boundary (e.g.
        # a Monday daily row that's also the bucket date for its
        # week), its pk is the SAME as ``new_row['pk']``. ``r.do``
        # does not guarantee delete-before-insert for overlapping
        # pks: under some evaluation orders the insert lands first,
        # then the delete removes it, and the bucket row vanishes
        # silently. Filter the colliding pk out of the delete list
        # and rely on ``conflict="replace"`` to overwrite that single
        # row in place.
        delete_pks = [s["pk"] for s in sources if s["pk"] != new_row["pk"]]
        bucket.take()
        try:
            if delete_pks:
                r.do(
                    r.table("usage_consumption")
                    .get_all(*delete_pks)
                    .delete(durability="hard"),
                    r.table("usage_consumption").insert(
                        new_row, conflict="replace", durability="hard"
                    ),
                ).run(conn)
            else:
                # Single-source case where the source's own pk is the
                # bucket pk: a plain replace is enough (no other rows
                # to clean up).
                r.table("usage_consumption").insert(
                    new_row, conflict="replace", durability="hard"
                ).run(conn)
            stats["aggregated"] += 1
            stats["replaced_sources"] += len(sources)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "rollup failed for %s/%s @ %s: %s",
                key[0],
                key[2],
                bucket_date.isoformat(),
                str(exc)[:200],
            )
            stats["errors"] += 1


def _scan_window(
    conn,
    start: datetime,
    end: datetime,
    retention: UsageRetentionConfig,
    stats: dict,
) -> dict:
    cursor = (
        r.table("usage_consumption")
        .filter((r.row["date"] >= start) & (r.row["date"] < end))
        .run(conn, array_limit=10_000_000)
    )
    groups: dict = defaultdict(list)
    for row in cursor:
        stats["scanned"] += 1
        tier = classify_tier(row["date"], retention)
        if tier is Tier.DAILY:
            continue
        groups[_bucket_key(row, tier)].append(row)
    return groups


def run_backfill(
    conn,
    retention: UsageRetentionConfig,
    *,
    qps: int = 10,
    dry_run: bool = False,
    stats: Optional[dict] = None,
    backup: Optional[BackupWriter] = None,
) -> dict:
    """Walk every row older than the safety margin. One-shot."""
    stats = stats if stats is not None else empty_stats()
    cutoff = _safety_cutoff(datetime.now(timezone.utc))
    log.info("backfill: scanning rows older than %s", cutoff.isoformat())
    cursor = (
        r.table("usage_consumption")
        .filter(r.row["date"] < cutoff)
        .run(conn, array_limit=10_000_000)
    )
    groups: dict = defaultdict(list)
    for row in cursor:
        stats["scanned"] += 1
        tier = classify_tier(row["date"], retention)
        if tier is Tier.DAILY:
            continue
        groups[_bucket_key(row, tier)].append(row)
    log.info(
        "backfill: %d rows scanned, %d groups to evaluate",
        stats["scanned"],
        len(groups),
    )
    bucket = TokenBucket(qps)
    _process_groups(
        conn,
        groups,
        dry_run=dry_run,
        bucket=bucket,
        stats=stats,
        retention=retention,
        backup=backup,
    )
    return stats


def run_incremental(
    conn,
    retention: UsageRetentionConfig,
    *,
    qps: int = 10,
    dry_run: bool = False,
    stats: Optional[dict] = None,
    backup: Optional[BackupWriter] = None,
) -> dict:
    """Process only the tier-transition windows (~14 days each)."""
    stats = stats if stats is not None else empty_stats()
    now = datetime.now(timezone.utc)
    cutoff = _safety_cutoff(now)
    boundaries: list[tuple[str, int]] = [
        ("daily->weekly", retention.daily_months * 30),
        ("weekly->monthly", retention.weekly_months * 30),
    ]
    if retention.total_months is not None:
        boundaries.append(("monthly->delete", retention.total_months * 30))

    bucket = TokenBucket(qps)
    for label, days in boundaries:
        window_end = min(now - timedelta(days=days - INCREMENTAL_WINDOW_DAYS), cutoff)
        window_start = now - timedelta(days=days + INCREMENTAL_WINDOW_DAYS)
        if window_start >= window_end:
            log.info("incremental: %s window empty (start>=end)", label)
            continue
        log.info(
            "incremental: %s window %s -> %s",
            label,
            window_start.isoformat(),
            window_end.isoformat(),
        )
        groups = _scan_window(conn, window_start, window_end, retention, stats)
        _process_groups(
            conn,
            groups,
            dry_run=dry_run,
            bucket=bucket,
            stats=stats,
            retention=retention,
            backup=backup,
        )
    return stats
