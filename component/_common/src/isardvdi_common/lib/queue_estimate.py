#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2026 IsardVDI
#
# SPDX-License-Identifier: AGPL-3.0-or-later

"""Live queue estimate for a single storage task: effective position + ETA.

``effective_position`` improves on RQ's raw single-lane ``job.get_position()``
by adding the backlog of every higher-priority tier in the same pool — the
governor drains ``interactive`` before ``standard`` before the governed tiers,
so a task's true wait is gated by the work ahead of it across ALL those lanes,
not just its own. It is an honest approximation (it does not model PSI-defer or
per-category fairness) but is strictly better than the raw position.

``eta_seconds`` is ``ceil(effective_position / effective_concurrency) *
service_time``, where ``service_time`` is a per-(tier, action) EWMA fed by
completed tasks (``record_service_time``); it is ``None`` until a sample exists.
Everything is bounded and never raises — a bad estimate must never break a task
read."""

import json
import math

from isardvdi_common.lib import queue_coverage, queue_tiers

_EMPTY = {
    "effective_position": None,
    "eta_seconds": None,
    "has_consumer": None,
    "stranded": None,
}

# Per-(tier, action) service-time EWMA. Written on each finished task, read to
# turn a queue position into a wall-clock ETA. Deliberately coarse: a fleet-mean
# blind to disk size, labelled an estimate in the UI.
_EWMA_PREFIX = "governor:svc:ewma"
_EWMA_ALPHA = 0.2
_EWMA_TTL = 7 * 24 * 3600
_SVC_MIN = 0.05  # ignore sub-50ms samples (no-op / not really run)
_SVC_MAX = 6 * 3600  # clamp outliers (a wedged 12h move must not skew the mean)
_GOVERNOR_CONFIG_KEY = "governor:config"
_DEFAULT_MAX_HEAVY = 2


def _decode(value):
    if isinstance(value, (bytes, bytearray)):
        return value.decode()
    return value


def _ewma_key(tier, action):
    return f"{_EWMA_PREFIX}:{tier}:{action}"


def record_service_time(conn, tier, action, seconds):
    """Fold one completed task's wall-clock into the (tier, action) EWMA.

    Best-effort and bounded: ignores sub-50ms and clamps multi-hour outliers so a
    single wedged job cannot poison the mean. Never raises."""
    if not tier or not action or seconds is None:
        return
    try:
        sample = float(seconds)
    except (TypeError, ValueError):
        return
    # Reject NaN/inf too: ``nan < _SVC_MIN`` is False, so a bare ``<`` check would
    # let NaN through and ``min(nan, _SVC_MAX)`` returns nan, poisoning the EWMA
    # (every later fold stays nan) for the whole 7-day TTL.
    if not math.isfinite(sample) or sample < _SVC_MIN:
        return
    sample = min(sample, _SVC_MAX)
    key = _ewma_key(tier, action)
    try:
        prev = conn.get(key)
        prev = float(_decode(prev)) if prev is not None else None
        new = (
            sample
            if prev is None
            else (_EWMA_ALPHA * sample + (1 - _EWMA_ALPHA) * prev)
        )
        conn.set(key, repr(new), ex=_EWMA_TTL)
    except Exception:
        return


def _read_service_time(conn, tier, action):
    """The (tier, action) EWMA seconds, falling back to a tier-wide sample, or
    ``None`` when nothing has been recorded yet."""
    for key in (_ewma_key(tier, action), f"{_EWMA_PREFIX}:{tier}"):
        try:
            raw = conn.get(key)
        except Exception:
            return None
        if raw is not None:
            try:
                return float(_decode(raw))
            except (TypeError, ValueError):
                return None
    return None


def _max_heavy(conn):
    try:
        raw = conn.get(_GOVERNOR_CONFIG_KEY)
        if raw is None:
            return _DEFAULT_MAX_HEAVY
        cfg = json.loads(_decode(raw))
        value = cfg.get("max_heavy")
        return int(value) if value is not None else _DEFAULT_MAX_HEAVY
    except Exception:
        return _DEFAULT_MAX_HEAVY


def _effective_concurrency(conn, covered, pool, tier):
    """Workers that drain this lane, capped by the global max-heavy limit for the
    heavy tiers (which additionally contend for the heavy-concurrency slots)."""
    try:
        count = covered.get((pool, tier), 0)
    except AttributeError:
        count = 0
    if tier in queue_tiers.HEAVY_TIERS:
        count = min(count, _max_heavy(conn))
    return max(1, count)


def _eta_seconds(conn, covered, pool, tier, action, effective_position):
    if effective_position is None:
        return None
    svc = _read_service_time(conn, tier, action)
    if svc is None:
        return None
    eff_conc = _effective_concurrency(conn, covered, pool, tier)
    return math.ceil(effective_position / eff_conc) * svc


# RQ stores a queue's job-id list at ``rq:queue:<name>``; an LLEN on the bare
# lane name reads a key that never exists (always 0). Every backlog read must
# prefix it, exactly like ``Queue(name).count`` does internally.
_RQ_QUEUE_PREFIX = "rq:queue:"


def _lane(pool, category, tier):
    # interactive/standard are always FLAT (never per-category); only the
    # governed/fair tiers carry a category segment. Match retier_queue so the
    # reconstructed lane name is the one RQ actually created — else a per-tenant
    # llen of a flat foreground tier would hit a nonexistent lane and read 0.
    if category and tier in queue_tiers._FAIR_TIERS:
        return f"storage.{pool}.{category}.{tier}"
    return f"storage.{pool}.{tier}"


def _higher_tier_backlog(conn, pool, category, tier):
    """Total queued jobs in the tiers that outrank ``tier`` in this pool."""
    try:
        idx = queue_tiers.TIERS.index(tier)
    except ValueError:
        return 0
    total = 0
    for higher in queue_tiers.TIERS[:idx]:
        try:
            total += conn.llen(_RQ_QUEUE_PREFIX + _lane(pool, category, higher))
        except Exception:
            continue
    return total


def estimate_task(task, conn=None):
    """``{effective_position, eta_seconds, has_consumer, stranded}`` for ``task``.

    ``effective_position`` is ``None`` unless the job is still queued.
    Fail-safe: any error yields all-``None`` rather than raising."""
    try:
        conn = conn or task._redis
        parsed = queue_tiers.parse_storage_queue(task.queue)
        if not parsed:
            return dict(_EMPTY)
        pool, category, tier = parsed

        result = dict(_EMPTY)
        covered = None
        try:
            covered, opaque_pools = queue_coverage.served_coverage(conn)
            if covered or opaque_pools:
                has_consumer = (pool, tier) in covered
                result["has_consumer"] = has_consumer
                result["stranded"] = (not has_consumer) and (pool not in opaque_pools)
        except Exception:
            covered = None

        raw_position = task.position  # job.get_position(); None unless queued
        if raw_position is not None:
            effective = _higher_tier_backlog(conn, pool, category, tier) + raw_position
            result["effective_position"] = effective
            if covered is not None:
                result["eta_seconds"] = _eta_seconds(
                    conn, covered, pool, tier, getattr(task, "task", None), effective
                )
        return result
    except Exception:
        return dict(_EMPTY)
