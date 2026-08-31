#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Durable shed / defer event counters on the governor redis namespace.

The producer-side shed gate and the worker-side PSI/cap deferral are both
*decisions that leave no trace*: a shed is a 429 the user sees and nobody else
does, and ``governor:worker:<name>.deferring`` is a point-in-time gauge — a
fast defer/undefer oscillation reads as "not deferring" on almost every poll.
This module gives both an audit trail with the cheapest primitives redis has:

* ``governor:counters:<kind>`` — a HASH of monotonic totals (``total``, one
  ``reason:<r>`` field per closed-set reason, one ``tier:<t>`` per known tier)
  plus the last event's context. Monotonic totals answer "did this EVER
  happen", which a gauge cannot.
* ``governor:counters:<kind>:m:<minute>`` — a per-minute STRING counter with a
  TTL just past the window, summed over :data:`WINDOW_MINUTES` on read. This is
  the *rate*: what makes a storm visible in a single sample.

Cardinality is bounded on purpose: reasons are mapped into a closed set and
tiers must be known tiers, so pool ids / worker names (unbounded over an
install's lifetime) are only ever kept as ``last_*`` context, never as counter
fields — the hash cannot grow.

Both sides are fail-open and NEVER raise: recording sits on the request path
that is about to return a 429 and inside the worker's hot dequeue loop, and a
redis blip in the observability layer must not change either behaviour.
"""

import time

from isardvdi_common.lib import queue_tiers

COUNTERS_PREFIX = "governor:counters"

SHED = "shed"
DEFER = "defer"

# Rolling rate window. Read sums this many per-minute buckets; buckets carry a
# TTL one minute past it so nothing accumulates.
WINDOW_MINUTES = 15
_BUCKET_TTL_SECONDS = (WINDOW_MINUTES + 1) * 60

# Closed reason sets — anything else collapses to ``other`` so a future caller
# cannot turn the totals hash into an unbounded key space.
# Do not import ``queue_coverage`` here: that module imports this one.
_REASONS = {
    SHED: frozenset({"no_consumer", "overloaded", "coverage_unreadable"}),
    DEFER: frozenset({"psi", "at_cap"}),
}
_OTHER_REASON = "other"


def totals_key(kind):
    """The monotonic-totals HASH key for ``shed`` / ``defer``."""
    return f"{COUNTERS_PREFIX}:{kind}"


def _bucket_key(kind, minute):
    return f"{COUNTERS_PREFIX}:{kind}:m:{minute}"


def empty_counters():
    """The never-recorded document — also what a read degrades to."""
    return {
        "total": 0,
        "recent": 0,
        "window_minutes": WINDOW_MINUTES,
        "by_reason": {},
        "by_tier": {},
        "last_ts": None,
        "last_seconds_ago": None,
        "last_reason": None,
        "last_pool": None,
        "last_tier": None,
        "last_worker": None,
    }


def _dec(value):
    if isinstance(value, (bytes, bytearray)):
        return value.decode()
    return value


def _int(value):
    try:
        return int(_dec(value))
    except (TypeError, ValueError):
        return 0


def _float(value):
    try:
        return float(_dec(value))
    except (TypeError, ValueError):
        return None


def _reason(kind, reason):
    reason = _dec(reason)
    return reason if reason in _REASONS.get(kind, frozenset()) else _OTHER_REASON


def _record(conn, kind, reason, pool=None, tier=None, worker=None, now=None):
    ts = time.time() if now is None else now
    reason = _reason(kind, reason)
    key = totals_key(kind)
    mapping = {"last_ts": repr(ts), "last_reason": reason}
    if pool is not None:
        mapping["last_pool"] = str(pool)
    if tier is not None:
        mapping["last_tier"] = str(tier)
    if worker is not None:
        mapping["last_worker"] = str(worker)
    bucket = _bucket_key(kind, int(ts // 60))
    try:
        with conn.pipeline() as pipe:
            pipe.hincrby(key, "total", 1)
            pipe.hincrby(key, f"reason:{reason}", 1)
            if tier in queue_tiers.TIERS:
                pipe.hincrby(key, f"tier:{tier}", 1)
            pipe.hset(key, mapping=mapping)
            pipe.incr(bucket)
            pipe.expire(bucket, _BUCKET_TTL_SECONDS)
            pipe.execute()
    except Exception:
        pass


def _read(conn, kind, now=None):
    ts = time.time() if now is None else now
    minute = int(ts // 60)
    buckets = [_bucket_key(kind, minute - offset) for offset in range(WINDOW_MINUTES)]
    try:
        with conn.pipeline() as pipe:
            pipe.hgetall(totals_key(kind))
            pipe.mget(buckets)
            raw_totals, raw_window = pipe.execute()
    except Exception:
        return empty_counters()

    doc = empty_counters()
    for raw_field, raw_value in (raw_totals or {}).items():
        field = _dec(raw_field)
        if field == "total":
            doc["total"] = _int(raw_value)
        elif field.startswith("reason:"):
            doc["by_reason"][field[len("reason:") :]] = _int(raw_value)
        elif field.startswith("tier:"):
            doc["by_tier"][field[len("tier:") :]] = _int(raw_value)
        elif field in ("last_reason", "last_pool", "last_tier", "last_worker"):
            doc[field] = _dec(raw_value)
        elif field == "last_ts":
            doc["last_ts"] = _float(raw_value)
    if doc["last_ts"] is not None:
        doc["last_seconds_ago"] = round(max(0.0, ts - doc["last_ts"]), 3)
    doc["recent"] = sum(_int(value) for value in (raw_window or []))
    return doc


def record_shed(conn, reason, pool=None, tier=None, now=None):
    """Count one producer-side shed rejection (a user-visible 429)."""
    _record(conn, SHED, reason, pool=pool, tier=tier, now=now)


def record_defer(conn, reason, worker=None, now=None):
    """Count one worker background-deferral event (a rising edge, not a poll)."""
    _record(conn, DEFER, reason, worker=worker, now=now)


def read_shed(conn, now=None):
    """Shed counters document; :func:`empty_counters` on any redis failure."""
    return _read(conn, SHED, now=now)


def read_defer(conn, now=None):
    """Defer counters document; :func:`empty_counters` on any redis failure."""
    return _read(conn, DEFER, now=now)
