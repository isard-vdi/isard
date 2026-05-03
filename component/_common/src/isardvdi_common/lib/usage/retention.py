#
#   Copyright © 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Date / bucket / pk helpers for the ``usage_consumption`` rollup.

Three tiers, age-based:

* ``DAILY``  — newer than ``daily_months`` → row stays as-is.
* ``WEEKLY`` — between ``daily_months`` and ``weekly_months`` → row
  belongs to the Monday-of-week bucket.
* ``MONTHLY`` — older than ``weekly_months`` → row belongs to the
  first-of-month bucket.

Optional ``total_months`` triggers a hard delete for anything older.

Both readers (``get_item_date_consumption``) and the rollup script
import these helpers so the bucket math has one definition.
"""

import hashlib
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Optional

from isardvdi_common.schemas.usage import UsageRetentionConfig
from rethinkdb import r

# Average days/month — matches the consolidator's existing "days
# before" arithmetic. We deliberately do NOT do calendar-month
# arithmetic for tier classification because the cutover only needs
# to be ~accurate (a row promoted a few days early or late changes
# nothing about the aggregation correctness).
_DAYS_PER_MONTH = 30


class Tier(Enum):
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    DELETE = "delete"


def save_config(conn, cfg: UsageRetentionConfig) -> None:
    """Persist ``cfg`` into ``config.id=1.usage_retention``.

    Caller is responsible for cross-field validation
    (:meth:`UsageRetentionConfig.assert_tier_ordering`); this function
    does the rdb write only.
    """
    r.table("config").get(1).update({"usage_retention": cfg.model_dump()}).run(conn)


def load_config(conn) -> UsageRetentionConfig:
    """Load the retention config from ``config.id=1.usage_retention``.

    Falls back to schema defaults when the field is absent (fresh
    install before the upgrade.py block has run, or admin removed
    the doc by hand). Also tolerates a missing ``config`` table —
    e.g. when the offline rollup script is pointed at a database
    that hasn't been initialised yet.
    """
    try:
        row = r.table("config").get(1).pluck("usage_retention").default({}).run(conn)
    except Exception:
        row = {}
    raw = (row or {}).get("usage_retention") or {}
    return UsageRetentionConfig.model_validate(raw)


def classify_tier(
    date: datetime, retention: UsageRetentionConfig, now: Optional[datetime] = None
) -> Tier:
    """Pick the bucket tier for ``date`` against ``retention``.

    ``now`` is injectable for deterministic tests.
    """
    if now is None:
        now = datetime.now(timezone.utc)
    age_days = (now - date).days
    if (
        retention.total_months is not None
        and age_days > retention.total_months * _DAYS_PER_MONTH
    ):
        return Tier.DELETE
    if age_days <= retention.daily_months * _DAYS_PER_MONTH:
        return Tier.DAILY
    if age_days <= retention.weekly_months * _DAYS_PER_MONTH:
        return Tier.WEEKLY
    return Tier.MONTHLY


def bucket_for(date: datetime, tier: Tier) -> datetime:
    """Round ``date`` to the start of its bucket for ``tier``.

    * ``DAILY`` — midnight UTC of the same day.
    * ``WEEKLY`` — Monday 00:00 UTC of the same ISO week.
    * ``MONTHLY`` — first-of-month 00:00 UTC.
    """
    midnight = date.astimezone(timezone.utc).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    if tier is Tier.DAILY:
        return midnight
    if tier is Tier.WEEKLY:
        # weekday() returns 0=Mon..6=Sun.
        return midnight - timedelta(days=midnight.weekday())
    if tier is Tier.MONTHLY:
        return midnight.replace(day=1)
    raise ValueError(f"bucket_for: tier={tier!r} has no bucket boundary")


def bucket_pk(
    item_id: str, item_type: str, item_consumer: str, bucket_date: datetime
) -> str:
    """Deterministic primary key for a rolled-up row.

    Mirrors the consolidator's ``gen_pk`` (md5 of joined fields) so
    a re-run of the rollup writes to the same row instead of creating
    duplicates. ``bucket_date`` is the bucket boundary, never the
    original daily date.
    """
    return hashlib.md5(
        (str(item_id) + item_type + item_consumer + bucket_date.isoformat()).encode(
            "utf-8"
        )
    ).hexdigest()
