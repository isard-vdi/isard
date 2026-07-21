#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Storage-lane consumer coverage and the producer-side shed decision.

A read-only view of the storage worker fleet built from the same governor redis
keys the admin backlog gauge uses, so the enqueue-time shed gate and the admin
view share ONE ``has_consumer`` / ``stranded`` definition. Everything here is
bounded (no ``KEYS`` glob, one pipelined pass over ``rq:workers``) and
**fail-open**: any redis error, or a fleet we cannot see, yields "ok / do not
shed" so a transient blip never rejects a user action.

Coverage model
--------------
Each live worker contributes the ``(pool, tier)`` pairs it serves:

* a **governor** worker publishes ``governor:worker:<name>.served_lanes`` (a
  JSON list, hash TTL 90s) — an exact served set;
* an **opaque** worker (a plain reserved / std-lane / notifier worker, or a
  not-yet-upgraded governed worker) has no governor hash, so we fall back to its
  RQ birth ``queues`` and record its pool as *opaque* — a lane in an opaque pool
  can never be declared stranded, because such a worker might serve overflow we
  cannot see.

``stranded(pool, tier)`` is therefore true only when NO live worker serves the
pair AND no opaque worker sits in that pool — i.e. we are confident the lane has
no consumer, which is exactly when a foreground task there would hang forever.
"""

import json
import os
import time
from collections import Counter

from isardvdi_common.lib import queue_tiers

try:  # rq is always present where a producer runs; guard so import never fails.
    from rq.defaults import DEFAULT_WORKER_TTL as _RQ_WORKER_TTL
    from rq.utils import utcparse as _utcparse
except Exception:  # pragma: no cover - rq missing (e.g. docs build)
    _RQ_WORKER_TTL = 420
    _utcparse = None

_RQ_WORKERS_KEY = "rq:workers"
_RQ_WORKER_PREFIX = "rq:worker:"
# RQ keeps a queue's job-id list at ``rq:queue:<name>`` — an LLEN on the bare
# lane name reads a nonexistent key (always 0), so the backlog cap would never
# fire. Prefix it, matching ``Queue(name).count``.
_RQ_QUEUE_PREFIX = "rq:queue:"
_GOVERNOR_WORKER_PREFIX = "governor:worker:"

# Interactive tiers: a user (or a system action on their behalf) is actively
# waiting, so these — and only these — may be rejected with a "retry later".
# Every other tier is deferrable/governed and only ever informs.
FOREGROUND_TIERS = frozenset({"interactive", "standard"})

# Per-tier backlog thresholds (LLEN of the target lane). Only foreground tiers
# carry a HARD cap that rejects even with a live consumer; every tier has a WARN
# threshold that marks the lane as backed up so the producer can inform. All are
# env-overridable so an operator can tune per install without a rebuild.
_HARD_CAP_DEFAULTS = {"interactive": 60, "standard": 150}
_WARN_DEFAULTS = {
    "interactive": 20,
    "standard": 50,
    "template": 10,
    "bulk": 500,
    "maintenance": 100,
    "reclaim": 200,
    "background": 1000,
}


def _env_int(name, default):
    raw = os.environ.get(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def hard_cap(tier):
    """Backlog above which a FOREGROUND lane rejects; ``None`` for governed
    tiers (which never reject on backlog)."""
    if tier not in _HARD_CAP_DEFAULTS:
        return None
    return _env_int(f"STORAGE_SHED_HARD_{tier.upper()}", _HARD_CAP_DEFAULTS[tier])


def warn_backlog(tier):
    """Backlog above which the lane is considered backed up (inform the user)."""
    return _env_int(
        f"STORAGE_SHED_WARN_{tier.upper()}", _WARN_DEFAULTS.get(tier, 10**9)
    )


def _dec(value):
    if isinstance(value, (bytes, bytearray)):
        return value.decode()
    return value


def _dec_hash(raw):
    if not raw:
        return {}
    return {_dec(k): _dec(v) for k, v in raw.items()}


def _worker_up(worker_hash, gov_hash, now_ts):
    """Live iff a governor hash is present (published within its 90s TTL) OR the
    RQ heartbeat is fresh (< 420s). Governor presence is the stronger signal;
    the heartbeat fallback keeps not-yet-upgraded / plain workers counted."""
    if gov_hash:
        return True
    hb_raw = worker_hash.get("last_heartbeat")
    if not hb_raw or _utcparse is None:
        return False
    try:
        return (now_ts - _utcparse(hb_raw).timestamp()) < _RQ_WORKER_TTL
    except Exception:
        return False


def _worker_lanes(worker_hash, gov_hash):
    """Return ``(served_lanes, known)``: the governor served set when published
    (``known=True``), else the RQ birth ``queues`` (``known=False``)."""
    if "served_lanes" in gov_hash:
        try:
            parsed = json.loads(gov_hash.get("served_lanes") or "[]")
            if isinstance(parsed, list):
                return [str(x) for x in parsed], True
        except Exception:
            pass
    birth = worker_hash.get("queues") or ""
    return [lane for lane in birth.split(",") if lane], False


def served_coverage(conn):
    """``(covered, opaque_pools)`` over the live fleet.

    ``covered`` is a ``Counter`` of ``(pool, tier)`` -> number of live workers
    serving that lane (membership still answers "has a consumer?", and the count
    feeds the ETA's effective concurrency); ``opaque_pools`` is the set of pools
    holding a live worker whose served set we cannot see. Raises on redis error
    (callers treat that as fail-open)."""
    covered = Counter()
    opaque_pools = set()
    members = conn.smembers(_RQ_WORKERS_KEY)
    worker_keys = [
        key
        for key in (_dec(m) for m in (members or []))
        if key and key.startswith(_RQ_WORKER_PREFIX)
    ]
    if not worker_keys:
        return covered, opaque_pools

    with conn.pipeline() as pipe:
        for key in worker_keys:
            pipe.hgetall(key)
            pipe.hgetall(_GOVERNOR_WORKER_PREFIX + key[len(_RQ_WORKER_PREFIX) :])
        results = pipe.execute()

    now_ts = time.time()
    for idx in range(len(worker_keys)):
        worker_hash = _dec_hash(results[idx * 2])
        gov_hash = _dec_hash(results[idx * 2 + 1])
        if not _worker_up(worker_hash, gov_hash, now_ts):
            continue
        lanes, known = _worker_lanes(worker_hash, gov_hash)
        birth_pool = None
        for lane in lanes:
            parsed = queue_tiers.parse_storage_queue(lane)
            if parsed:
                covered[(parsed[0], parsed[2])] += 1
                if birth_pool is None:
                    birth_pool = parsed[0]
        if not known and birth_pool:
            opaque_pools.add(birth_pool)
    return covered, opaque_pools


def lane_shed_decision(conn, queue):
    """Decide what to do with a task about to enqueue on ``queue``.

    Returns ``(decision, ctx)`` where ``decision`` is ``"reject"`` (no live
    consumer for the lane, any tier; or a foreground lane above its hard cap),
    ``"warn"`` (backed up but will run) or ``"ok"``. ``ctx`` carries ``pool``/
    ``category``/``tier``/``backlog``/``has_consumer``/``stranded``/``reason``
    for the caller's error or notify. Never raises — any failure degrades to
    ``("ok", ...)``."""
    parsed = queue_tiers.parse_storage_queue(queue)
    if not parsed:
        return "ok", {"reason": "non_storage_queue"}
    pool, category, tier = parsed
    try:
        covered, opaque_pools = served_coverage(conn)
        if not covered and not opaque_pools:
            # No worker visible at all — a full-fleet restart blip is far more
            # likely than a deliberate zero-consumer state; fail open.
            return "ok", {
                "reason": "no_coverage_data",
                "pool": pool,
                "category": category,
                "tier": tier,
            }
        backlog = conn.llen(_RQ_QUEUE_PREFIX + queue)
    except Exception:
        return "ok", {
            "reason": "coverage_error",
            "pool": pool,
            "category": category,
            "tier": tier,
        }

    has_consumer = (pool, tier) in covered
    stranded = (not has_consumer) and (pool not in opaque_pools)
    ctx = {
        "pool": pool,
        "category": category,
        "tier": tier,
        "backlog": backlog,
        "has_consumer": has_consumer,
        "stranded": stranded,
    }

    # A lane with NO live consumer is refused for EVERY tier: a task nothing can
    # drain must not be enqueued — it would strand forever. Because the lane is
    # per-(pool, category), the refusal is naturally scoped to the categories a
    # dead pool serves. A live-but-busy consumer is not stranded: foreground
    # gets the extra hard-cap rule below, governed tiers still accumulate.
    if stranded:
        return "reject", {**ctx, "reason": "no_consumer"}

    if tier in FOREGROUND_TIERS:
        cap = hard_cap(tier)
        if cap is not None and backlog >= cap:
            return "reject", {**ctx, "reason": "overloaded", "hard_cap": cap}

    if backlog >= warn_backlog(tier):
        return "warn", {**ctx, "reason": "backlog", "warn": warn_backlog(tier)}
    return "ok", ctx


def _raise_lane_429(ctx):
    """Raise the typed 429 ``Error`` for a rejected lane, carrying its
    (pool, category, tier) so the caller can surface a category-scoped notice.

    Imported lazily: resolves to apiv4's rich Error (→ 429) in-process, or to
    ErrorBase elsewhere; both carry the status code + description_code."""
    from isardvdi_common.helpers.error_factory import Error

    code = (
        "storage_no_consumer_retry_later"
        if ctx.get("reason") == "no_consumer"
        else "storage_overloaded_retry_later"
    )
    raise Error(
        "too_many_requests",
        f"Storage lane {ctx.get('pool')}/{ctx.get('tier')} is temporarily "
        "unable to accept work; please retry shortly",
        description_code=code,
        params={
            "pool": ctx.get("pool"),
            "category": ctx.get("category"),
            "tier": ctx.get("tier"),
        },
    )


def check_no_consumer(conn, queue):
    """Raise a typed 429 when ``queue`` has NO live consumer for its
    (pool, category) — a task nothing can drain must never be enqueued, for any
    tier. Mandatory on every producer and category-scoped (a dead pool only
    refuses the categories it serves); fail-open on any coverage uncertainty.
    Distinct from :func:`check_shed`, the opt-in backlog-overload gate."""
    decision, ctx = lane_shed_decision(conn, queue)
    if decision == "reject" and ctx.get("reason") == "no_consumer":
        _raise_lane_429(ctx)


def check_shed(conn, queue):
    """Raise a typed 429 ``Error`` if a task must not enqueue on ``queue``
    (stranded for any tier, or a foreground lane above its hard backlog cap).
    Call this BEFORE any state mutation so a reject leaves nothing half-done.
    Fail-open on any coverage uncertainty."""
    decision, ctx = lane_shed_decision(conn, queue)
    if decision == "reject":
        _raise_lane_429(ctx)


def enforce_shed(conn, kwargs):
    """create_task gate with two independent rules:

    * **Mandatory** — refuse to enqueue on a lane with no live consumer
      (:func:`check_no_consumer`), for every producer and every tier, scoped to
      the lane's own (pool, category). A task nothing can drain must not be
      enqueued.
    * **Opt-in** — when the caller passes ``shed=True``, additionally apply the
      backlog-overload gate (:func:`check_shed`) for foreground lanes.

    Pops the ``shed`` kwarg so it never reaches ``Task``."""
    shed = kwargs.pop("shed", False)
    queue = kwargs.get("queue")
    if not queue:
        return
    check_no_consumer(conn, queue)
    if shed:
        check_shed(conn, queue)
