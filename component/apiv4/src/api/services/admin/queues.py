#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import json
import os
import time
import traceback
from datetime import datetime, timezone
from typing import Any, Optional

from api.services.error import Error
from cachetools import cached
from isardvdi_common.connections.redis_base import RedisBase
from isardvdi_common.connections.redis_urls import RQ_DB
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
from isardvdi_common.lib.governed_worker import (
    _LIVE_STATUSES,
    CATEGORY_RUNNING_PREFIX,
    HEAVY_RUNNING_KEY,
    WORKER_STATUS_PREFIX,
    category_running_key,
)
from isardvdi_common.lib.queue_tiers import (
    _FAIR_TIERS,
    NULL_CATEGORY,
    parse_storage_queue,
)
from isardvdi_common.lib.users.categories.categories import (
    CategoriesProcessed as CommonCategories,
)
from isardvdi_common.models.config import Config
from isardvdi_common.models.task import Task
from redis import Redis
from rq import Queue
from rq.defaults import DEFAULT_WORKER_TTL
from rq.job import Job, parse_job_id
from rq.results import Result
from rq.utils import utcparse

QUEUE_REGISTRIES = [
    "queued",
    "started",
    "finished",
    "failed",
    "deferred",
    "scheduled",
    "canceled",
]

# Presentation defaults for the live storage-governor block. These mirror the
# worker's env/hardcoded fallbacks; they are only what the admin view shows for
# an unset block — the worker does its own DB->env->hardcoded merge.
STORAGE_SCHEDULER_DEFAULTS = {
    "enabled": True,
    "psi_limit": 40.0,
    "max_heavy": 2,
    "backoff": 3,
    # Per-category fairness (elastic pool bulk/maintenance): weighted-RR weights,
    # per-category in-flight caps, and the default cap for categories without an
    # explicit one. Default cap None == uncapped (weighted-RR-only, work-conserving).
    "category_weights": {},
    "category_max_inflight": {},
    "category_default_max_inflight": None,
}

# Redis STRING (JSON) the elastic storage workers read their live config from.
# isard-storage may run on a different host from isard-db and must never open a
# RethinkDB connection, so apiv4 (which reaches both) mirrors the raw
# ``config[1].storage_scheduler`` block here — into the shared RQ Redis the
# workers already use — and the worker merges it DB->env->hardcoded per poll.
GOVERNOR_CONFIG_KEY = "governor:config"

queues_cache = SynchronizedTTLCache(maxsize=1, ttl=5)
queue_jobs_cache = SynchronizedTTLCache(maxsize=20, ttl=5)
consumers_cache = SynchronizedTTLCache(maxsize=1, ttl=5)
# Read-only storage-governor gauge caches (5s TTL so a polling dashboard cannot
# hammer Redis). These are gauges, not mutated by admin writes, so they are not
# wired into clear_queue_data_caches.
governor_cache = SynchronizedTTLCache(maxsize=1, ttl=5)
backlog_cache = SynchronizedTTLCache(maxsize=1, ttl=5)
category_names_cache = SynchronizedTTLCache(maxsize=1, ttl=5)
# maxsize>1: list_problem_tasks is keyed on (kind, pool, category_id, tier,
# limit, offset), so distinct filter/page combinations must each get their own
# cache slot instead of thrashing a single entry.
problem_tasks_cache = SynchronizedTTLCache(maxsize=64, ttl=5)

# Bounded-scan caps (internal safety limits). A cap that bites is surfaced via
# the truncated_* honesty fields, not silently dropped.
MAX_LANES = 500
MAX_INFLIGHT_SCAN = 2000
MAX_STARTED = 500
# Overall cap on job ids scanned across all target lanes by list_problem_tasks;
# a cap that bites is surfaced via the response ``truncated`` honesty flag.
MAX_PROBLEM_SCAN = 2000

# Batch size for the read-only leak scan's Job.fetch_many round-trips.
_INFLIGHT_FETCH_BATCH = 1000

# rq internal set/key prefixes we read (bounded), never a keys()/pubsub glob.
_RQ_QUEUES_KEY = "rq:queues"
_RQ_QUEUE_PREFIX = "rq:queue:"
_RQ_WORKERS_KEY = "rq:workers"
_RQ_WORKER_PREFIX = "rq:worker:"
# Source of truth for the per-worker status hash key is governed_worker; keep the
# reader and the publisher on the same schema.
_GOVERNOR_WORKER_PREFIX = WORKER_STATUS_PREFIX + ":"


def clear_queue_data_caches() -> None:
    """Invalidate queue-data caches after admin mutations that change job counts."""
    queues_cache.clear()
    queue_jobs_cache.clear()


def clear_governor_caches() -> None:
    """Invalidate the read-only storage-governor gauge caches (used by tests and
    any caller needing a fresh read; otherwise 5s-TTL-cached)."""
    governor_cache.clear()
    backlog_cache.clear()
    consumers_cache.clear()
    category_names_cache.clear()
    problem_tasks_cache.clear()


def _connect_redis() -> Redis:
    return Redis(
        host=os.environ.get("REDIS_HOST") or "isard-redis",
        port=int(os.environ.get("REDIS_PORT") or 6379),
        password=os.environ.get("REDIS_PASSWORD", ""),
        db=RQ_DB,
    )


# =============================================================================
# STORAGE-GOVERNOR read-layer helpers (pure / read-only — P2.4 §2.2)
#
# Every enumeration here is bounded: ONE SMEMBERS of the RQ-maintained
# ``rq:queues`` / ``rq:workers`` sets, filtered + capped. We NEVER call
# ``Queue.all()``, ``redis.keys("...*")`` or ``redis.pubsub_channels()``, and we
# never write (no SREM/SET/HSET), so a polled gauge cannot mutate the state it
# measures.
# =============================================================================


def _decode(value: Any) -> Optional[str]:
    """Redis returns bytes; normalise to str (or None)."""
    if value is None:
        return None
    if isinstance(value, (bytes, bytearray)):
        return value.decode()
    return str(value)


def _decode_hash(raw: Any) -> dict:
    """Decode a HGETALL result (bytes->str keys and values)."""
    out = {}
    for k, v in (raw or {}).items():
        dk = _decode(k)
        if dk is not None:
            out[dk] = _decode(v)
    return out


def _parse_category_running_key(key: str) -> Optional[tuple]:
    """Recover ``(pool, category)`` from a ``governor:running:<pool>:<category>``
    key.

    ``pool`` may itself be a colon-joined cross-pool ``src:dst`` key (5 colon
    fields total), so the category is split off the RIGHT — strip the
    ``governor:running:`` prefix then ``rsplit(":", 1)`` — never a naive
    left-to-right ``split`` that would mis-parse ``src`` as the pool.
    """
    prefix = CATEGORY_RUNNING_PREFIX + ":"  # "governor:running:"
    if not isinstance(key, str) or not key.startswith(prefix):
        return None
    rest = key[len(prefix) :]
    pool, sep, category = rest.rpartition(":")
    if not sep or not pool or not category:
        return None
    return (pool, category)


def _job_is_live(job: Optional[Job]) -> bool:
    """A set member is 'live' (legitimately holding its slot) iff its job still
    exists AND its status is in ``_LIVE_STATUSES``. A missing job (``None`` from
    ``fetch_many``) counts as NOT live -> leaked. Read-only mirror of the
    worker's ``_prune_stale_members`` decision (never SREMs)."""
    if job is None:
        return False
    try:
        status = job.get_status(refresh=False)
    except Exception:
        return False
    return status in _LIVE_STATUSES


def _leak_scan(conn, set_members: dict) -> tuple:
    """Read-only leak scan over Redis SET members that are BARE job ids.

    ``set_members`` maps ``set_key -> [job_id, ...]`` (already SMEMBER'd). We
    fetch the UNIQUE ids with ``Job.fetch_many`` (batched), capped at
    ``MAX_INFLIGHT_SCAN`` total, and mark each id live/leaked. Per set,
    ``leak = len(members) - live`` (a member with an unfetched/unknown status is
    counted as live so the leak can only ever under-report, mirroring the
    'a leak only under-admits' invariant). NEVER SREMs.

    Returns ``({set_key: {"count", "live", "leaked"}}, truncated_inflight)``.
    """
    unique_ids = []
    seen = set()
    for members in set_members.values():
        for m in members:
            if m is not None and m not in seen:
                seen.add(m)
                unique_ids.append(m)
    truncated_inflight = max(0, len(unique_ids) - MAX_INFLIGHT_SCAN)
    scan_ids = unique_ids[:MAX_INFLIGHT_SCAN]

    live_by_id: dict = {}
    for i in range(0, len(scan_ids), _INFLIGHT_FETCH_BATCH):
        batch = scan_ids[i : i + _INFLIGHT_FETCH_BATCH]
        try:
            jobs = Job.fetch_many(batch, connection=conn)
        except Exception:
            # A malformed batch must not wedge the gauge; treat as unknown->live.
            for jid in batch:
                live_by_id[jid] = True
            continue
        for jid, job in zip(batch, jobs):
            live_by_id[jid] = _job_is_live(job)

    result = {}
    for key, members in set_members.items():
        count = len(members)
        # Unknown (beyond the cap / unfetched) members default to live=True so
        # leak is never over-reported.
        live = sum(1 for m in members if live_by_id.get(m, True))
        result[key] = {
            "count": count,
            "live": live,
            "leaked": max(0, count - live),
        }
    return result, truncated_inflight


def _redis_health(conn) -> dict:
    """PING latency + INFO memory/evictions (catalog #15). Raises on a dead
    connection so the caller degrades to ``up=false``."""
    t0 = time.monotonic()
    conn.ping()
    ping_ms = (time.monotonic() - t0) * 1000.0
    info = conn.info()
    used = info.get("used_memory")
    maxmem = info.get("maxmemory")
    used_ratio = None
    if used is not None and maxmem:
        try:
            used_ratio = float(used) / float(maxmem) if float(maxmem) > 0 else 0.0
        except (TypeError, ValueError, ZeroDivisionError):
            used_ratio = None
    return {
        "up": True,
        "ping_ms": round(ping_ms, 3),
        "used_memory": int(used) if used is not None else None,
        "maxmemory": int(maxmem) if maxmem is not None else None,
        "used_ratio": round(used_ratio, 4) if used_ratio is not None else None,
        "evicted_keys": (
            int(info.get("evicted_keys"))
            if info.get("evicted_keys") is not None
            else None
        ),
    }


def _worker_kind(birth_tiers: set, gov_hash: dict) -> Optional[str]:
    """Best-effort worker class: the ``governor:worker:<name>`` hash carries it
    once published; until then infer from the birth queue tiers (any fair tier ->
    elastic, else reserved)."""
    if gov_hash.get("kind"):
        return gov_hash["kind"]
    if not birth_tiers:
        return None
    if birth_tiers & _FAIR_TIERS:
        return "elastic"
    return "reserved"


def _build_worker_row(
    name: str,
    worker_hash: dict,
    gov_hash: dict,
    now_dt: datetime,
    current_lane: Optional[str] = None,
) -> dict:
    """Assemble one worker health row from the ``rq:worker:<name>`` hash and the
    (not-yet-published) ``governor:worker:<name>`` hash. PURE — takes already
    decoded dicts so heartbeat/degradation logic is unit-testable.

    ``up`` is HEARTBEAT truth: the hash is present/non-empty AND
    ``now - last_heartbeat < DEFAULT_WORKER_TTL (420s)``. A worker present in the
    ``rq:workers`` SET but with an absent/empty hash (SIGKILLed, never removed
    from the SET) is ``up=false, hash_present=false``.
    """
    hash_present = bool(worker_hash)

    last_heartbeat = None
    heartbeat_age = None
    hb_raw = worker_hash.get("last_heartbeat")
    if hb_raw:
        try:
            hb_dt = utcparse(hb_raw)
            last_heartbeat = hb_dt.timestamp()
            heartbeat_age = (now_dt - hb_dt).total_seconds()
        except Exception:
            last_heartbeat = None
            heartbeat_age = None

    up = bool(
        hash_present
        and heartbeat_age is not None
        and heartbeat_age < DEFAULT_WORKER_TTL
    )

    # Birth queues (comma-separated) -> storage lanes / tiers / pool.
    birth_lanes = []
    q_raw = worker_hash.get("queues")
    if q_raw:
        birth_lanes = [q for q in q_raw.split(",") if q]
    storage_lanes = []
    birth_tiers = set()
    pool = None
    for lane in birth_lanes:
        parsed = parse_storage_queue(lane)
        if parsed:
            storage_lanes.append(lane)
            birth_tiers.add(parsed[2])
            if pool is None:
                pool = parsed[0]

    # served_lanes / served_known / PSI / flags come from governor:worker:<name>
    # (published in a later step). Until then, degrade: served_known=false and
    # a best-effort served set = the birth storage lanes.
    served_known = "served_lanes" in gov_hash
    served_lanes = storage_lanes
    if served_known:
        try:
            parsed_served = json.loads(gov_hash.get("served_lanes") or "[]")
            if isinstance(parsed_served, list):
                served_lanes = [str(x) for x in parsed_served]
        except Exception:
            served_known = False

    def _gov_float(key):
        val = gov_hash.get(key)
        if val is None:
            return None
        try:
            return float(val)
        except (TypeError, ValueError):
            return None

    def _gov_bool(key):
        if key not in gov_hash or gov_hash.get(key) is None:
            return None
        return str(gov_hash[key]).strip().lower() in ("1", "true", "yes", "on")

    return {
        "id": name,
        "queue": pool or "storage",
        "name": name,
        "pool": gov_hash.get("pool") or pool,
        "kind": _worker_kind(birth_tiers, gov_hash),
        "state": worker_hash.get("state"),
        "up": up,
        "hash_present": hash_present,
        "last_heartbeat": last_heartbeat,
        "heartbeat_age_seconds": (
            round(heartbeat_age, 3) if heartbeat_age is not None else None
        ),
        "current_lane": current_lane,
        "served_lanes": served_lanes,
        "served_known": served_known,
        "psi_cpu": _gov_float("psi_cpu"),
        "psi_io": _gov_float("psi_io"),
        "psi_mem": _gov_float("psi_mem"),
        "deferring": _gov_bool("deferring"),
        "at_cap": _gov_bool("at_cap"),
        "floor": _gov_bool("floor"),
        "multitenancy": _gov_bool("multitenancy"),
        "last_job_id": gov_hash.get("last_job_id"),
        "last_job_action": gov_hash.get("last_job_action"),
        "status": "ok" if up else "error",
    }


def _lane_stats(conn, lane: str, now_ts: float) -> dict:
    """Per-lane counts + head-only oldest-queued-age + started-over-timeout.

    Registry reads pass ``cleanup=False`` — a ``StartedJobRegistry`` read with
    ``cleanup=True`` MOVES timed-out jobs to ``FailedJobRegistry`` (a WRITE).
    Oldest-queued-age is HEAD ONLY: ``Queue.get_job_ids(0, 1)`` -> ``lrange 0 0``
    (never ``(0, 0)`` which is a full LRANGE), then one ``Job.fetch_many`` of the
    single head.
    """
    queue = Queue(lane, connection=conn)
    try:
        queued = queue.count
    except Exception:
        queued = 0
    started = _safe_registry_count(queue.started_job_registry)
    failed = _safe_registry_count(queue.failed_job_registry)
    deferred = _safe_registry_count(queue.deferred_job_registry)

    oldest_age = None
    try:
        head_ids = queue.get_job_ids(0, 1)  # HEAD ONLY (offset=0, length=1)
    except Exception:
        head_ids = []
    if head_ids:
        try:
            jobs = Job.fetch_many(head_ids, connection=conn)
            head = jobs[0] if jobs else None
            if head is not None and head.enqueued_at is not None:
                oldest_age = max(0.0, now_ts - head.enqueued_at.timestamp())
        except Exception:
            oldest_age = None

    started_over = 0
    try:
        started_ids = queue.started_job_registry.get_job_ids(
            0, MAX_STARTED - 1, cleanup=False
        )
    except Exception:
        started_ids = []
    if started_ids:
        try:
            jobs = Job.fetch_many(
                [parse_job_id(i) for i in started_ids], connection=conn
            )
            for job in jobs:
                if job is None or job.started_at is None or not job.timeout:
                    continue
                if now_ts - job.started_at.timestamp() > job.timeout:
                    started_over += 1
        except Exception:
            started_over = 0

    return {
        "queued": queued,
        "started": started,
        "started_over_timeout": started_over,
        "failed": failed,
        "deferred": deferred,
        "oldest_queued_age_seconds": oldest_age,
    }


def _safe_registry_count(registry) -> int:
    """``registry.count`` runs cleanup (a WRITE for StartedJobRegistry); always
    read with ``get_job_count(cleanup=False)``."""
    try:
        return int(registry.get_job_count(cleanup=False))
    except Exception:
        return 0


def _storage_lane_snapshot(conn) -> tuple:
    """ONE bounded ``SMEMBERS rq:queues`` snapshot, filtered to ``storage.*``
    lanes via ``parse_storage_queue``, sorted by backlog (LLEN) desc, capped at
    ``MAX_LANES``. Returns ``([(pool, category, tier, lane_name), ...],
    truncated_lanes)``. ``rq:queues`` members are full ``rq:queue:<name>`` keys.
    """
    members = conn.smembers(_RQ_QUEUES_KEY)
    lanes = []
    for raw in members or []:
        key = _decode(raw)
        if not key or not key.startswith(_RQ_QUEUE_PREFIX):
            continue
        lane = key[len(_RQ_QUEUE_PREFIX) :]
        parsed = parse_storage_queue(lane)
        if not parsed:
            continue
        pool, category, tier = parsed
        lanes.append((pool, category, tier, lane))

    if lanes:
        try:
            with conn.pipeline() as pipe:
                for _, _, _, lane in lanes:
                    pipe.llen(_RQ_QUEUE_PREFIX + lane)
                counts = pipe.execute()
        except Exception:
            counts = [0] * len(lanes)
    else:
        counts = []

    order = sorted(
        range(len(lanes)),
        key=lambda i: (counts[i] if i < len(counts) and counts[i] else 0),
        reverse=True,
    )
    ordered = [lanes[i] for i in order]
    truncated = max(0, len(ordered) - MAX_LANES)
    return ordered[:MAX_LANES], truncated


# =============================================================================
# PROBLEM-TASK listing helpers (P2.4 §7/3 — bounded, dangling-safe, read-only)
# =============================================================================

# Per-kind registry + (retryable, cancelable) + whether the registry stores
# composite ``{job_id}:{execution_id}`` members that must be parsed first.
_PROBLEM_KINDS = ("failed", "stuck_running", "deferred_orphan")


def _dt_to_ts(dt) -> Optional[float]:
    """A tz-aware rq-job datetime -> epoch float wire form (guarding None)."""
    if dt is None:
        return None
    try:
        return dt.timestamp()
    except Exception:
        return None


def _job_exc_string(job) -> Optional[str]:
    """Traceback of the job's latest FAILED result (``None`` otherwise).

    Uses ``job.latest_result()`` and ``Result.exc_string`` (a real instance
    attr) rather than the deprecated ``job.exc_info``; only a ``FAILED`` result
    carries a traceback. Best-effort — never raises out."""
    try:
        res = job.latest_result()
    except Exception:
        return None
    try:
        if res is not None and res.type == Result.Type.FAILED:
            return res.exc_string
    except Exception:
        return None
    return None


def _problem_kind_registry(queue, kind: str):
    """Map a problem ``kind`` to its ``(registry, retryable, cancelable,
    is_started)`` on a lane's ``Queue``."""
    if kind == "failed":
        return queue.failed_job_registry, True, True, False
    if kind == "stuck_running":
        return queue.started_job_registry, False, True, True
    # deferred_orphan
    return queue.deferred_job_registry, False, True, False


class AdminQueuesService:
    """Service for admin queue management operations."""

    @staticmethod
    @cached(queues_cache)
    def get_queues() -> list[dict]:
        """Get all queues with job counts."""
        with _connect_redis() as redis_conn:
            queues = Queue.all(connection=redis_conn)
        data = []
        for queue in queues:
            q = AdminQueuesService._get_queue_jobs(queue.name)
            q["id"] = queue.name
            data.append(q)
        return data

    @staticmethod
    @cached(queue_jobs_cache)
    def _get_queue_jobs(queue_name: str) -> dict:
        """Get job counts for a specific queue."""
        with _connect_redis() as redis_conn:
            queue = Queue(queue_name, connection=redis_conn)
        return {
            "queued": queue.count,
            "started": queue.started_job_registry.count,
            "finished": queue.finished_job_registry.count,
            "failed": queue.failed_job_registry.count,
            "deferred": queue.deferred_job_registry.count,
            "scheduled": queue.scheduled_job_registry.count,
            "canceled": queue.canceled_job_registry.count,
        }

    # -------------------------------------------------------------------------
    # Storage-governor read layer (P2.4 §2.2). Every method is 5s-TTL-cached so a
    # polling dashboard cannot hammer Redis, degrades to 200 + honesty fields on
    # transient Redis/rdb failure (never raises), and is read-only.
    # -------------------------------------------------------------------------

    @staticmethod
    @cached(consumers_cache)
    def get_consumers() -> list[dict]:
        """Worker health from HEARTBEAT (reworked; replaces the pubsub
        ``_subscribers`` + ``keys('rq:workers:*')`` ``_workers`` code).

        Enumerates the bounded ``rq:workers`` SET, loads each ``rq:worker:<name>``
        hash directly (NOT via ``Worker.all()`` / ``find_by_key`` — that SREMs a
        member whose hash is absent, a WRITE, and hides it), and reports
        heartbeat truth (``up``/``hash_present``/``heartbeat_age_seconds``) plus
        the served/PSI fields (degraded until ``governor:worker:<name>`` is
        published). Back-compatible ``QueueConsumerResponse`` shape (id/queue/
        status) PLUS the new fields. Returns 200-safe (``[]``) on Redis failure.
        """
        try:
            with _connect_redis() as conn:
                rows, _mt = AdminQueuesService._worker_health_rows(conn)
            return rows
        except Exception:
            return []

    @staticmethod
    def _worker_health_rows(conn) -> tuple:
        """Build worker rows + the worker-reported ``multitenancy_active`` flag
        from the bounded ``rq:workers`` SET. Shared by ``get_consumers`` and
        ``get_governor`` so both see the same heartbeat truth."""
        now_dt = datetime.now(timezone.utc)
        members = conn.smembers(_RQ_WORKERS_KEY)  # bounded RQ-maintained SET
        worker_keys = []
        for raw in members or []:
            key = _decode(raw)
            if key and key.startswith(_RQ_WORKER_PREFIX):
                worker_keys.append(key)

        # Batch-load the rq:worker + governor:worker hashes (no keys() glob).
        worker_hashes = {}
        gov_hashes = {}
        current_job_ids = {}
        try:
            with conn.pipeline() as pipe:
                for key in worker_keys:
                    pipe.hgetall(key)
                    name = key[len(_RQ_WORKER_PREFIX) :]
                    pipe.hgetall(_GOVERNOR_WORKER_PREFIX + name)
                results = pipe.execute()
        except Exception:
            results = []
        for idx, key in enumerate(worker_keys):
            name = key[len(_RQ_WORKER_PREFIX) :]
            wh = _decode_hash(results[idx * 2]) if idx * 2 < len(results) else {}
            gh = (
                _decode_hash(results[idx * 2 + 1]) if idx * 2 + 1 < len(results) else {}
            )
            worker_hashes[name] = wh
            gov_hashes[name] = gh
            cur = wh.get("current_job")
            if cur:
                current_job_ids[name] = cur

        # Resolve each worker's current-lane from its current job's origin in one
        # batched fetch (bounded by worker count).
        current_lanes = {}
        if current_job_ids:
            names = list(current_job_ids.keys())
            try:
                jobs = Job.fetch_many(
                    [current_job_ids[n] for n in names], connection=conn
                )
                for n, job in zip(names, jobs):
                    if job is not None and getattr(job, "origin", None):
                        current_lanes[n] = job.origin
            except Exception:
                current_lanes = {}

        rows = []
        reported = []
        for key in worker_keys:
            name = key[len(_RQ_WORKER_PREFIX) :]
            row = _build_worker_row(
                name,
                worker_hashes.get(name, {}),
                gov_hashes.get(name, {}),
                now_dt,
                current_lane=current_lanes.get(name),
            )
            rows.append(row)
            if row["up"] and row["multitenancy"] is not None:
                reported.append(row["multitenancy"])

        if not reported:
            multitenancy_active = "unknown"
        else:
            multitenancy_active = any(reported)
        return rows, multitenancy_active

    @staticmethod
    @cached(category_names_cache)
    def _category_name_map() -> dict:
        """Batched, TTL-cached ``{category_id: name}`` (+ the sentinel labels).

        Delegates the DB read to ``isardvdi_common`` (apiv4 skill B1 — services
        never open a RethinkDB connection). Maps the null-owner sentinel
        ``_nocat`` -> 'No category / system' and the flat (None-category) marker
        ``_none``; a deleted-owner id falls back to the raw id at the call site.
        """
        try:
            mapping = dict(CommonCategories.get_id_name_map() or {})
        except Exception:
            mapping = {}
        mapping[NULL_CATEGORY] = "No category / system"
        mapping["_none"] = "_none"
        return mapping

    @staticmethod
    def _resolve_category_name(category_id: Optional[str], names: dict) -> str:
        """Friendly name for a lane category id (None -> the ``_none`` flat
        marker), falling back to the raw id for a deleted owner."""
        key = category_id if category_id is not None else "_none"
        return names.get(key, key)

    @staticmethod
    @cached(governor_cache)
    def get_governor() -> dict:
        """Composite storage-governor gauge document (P2.4 §2.4).

        Read-only + bounded: ONE ``rq:queues`` snapshot, ``SCARD``-class heavy /
        per-category inflight with a batched read-only leak scan, heartbeat
        worker health, Redis health, and the effective (never re-published)
        config. Degrades to 200 + honesty fields (``redis.up=false``,
        ``multitenancy_active='unknown'``, empty pools/workers) on transient
        Redis/rdb failure rather than raising — a polled 500 would eject the
        operator mid-incident.
        """
        generated_at = time.time()
        try:
            return AdminQueuesService._build_governor(generated_at)
        except Error:
            raise
        except Exception:
            return AdminQueuesService._degraded_governor(generated_at)

    @staticmethod
    def _degraded_governor(generated_at: float) -> dict:
        """The honest 200 body served when Redis (or the whole read) is down."""
        return {
            "generated_at": generated_at,
            "data_age_seconds": 0.0,
            "multitenancy_active": "unknown",
            "config_enabled": STORAGE_SCHEDULER_DEFAULTS["enabled"],
            "config_mirrored": False,
            "psi_limit": STORAGE_SCHEDULER_DEFAULTS["psi_limit"],
            "redis": {"up": False},
            "heavy": {"running": 0, "cap": 0, "at_cap": False, "leaked": 0},
            "pools": [],
            "workers": [],
            "warnings": [],
            "truncated_lanes": 0,
            "truncated_inflight": 0,
            "config": None,
        }

    @staticmethod
    def _effective_config(block: dict) -> dict:
        """Effective/clamped config the elastic workers enforce (raw
        ``governor:config`` merged over the presentation defaults). Presentation
        only — the worker does its own per-key DB->env->hardcoded merge."""
        block = block or {}
        return {
            "enabled": bool(
                block.get("enabled", STORAGE_SCHEDULER_DEFAULTS["enabled"])
            ),
            "psi_limit": float(
                block.get("psi_limit", STORAGE_SCHEDULER_DEFAULTS["psi_limit"])
            ),
            "max_heavy": int(
                block.get("max_heavy", STORAGE_SCHEDULER_DEFAULTS["max_heavy"])
            ),
            "backoff": int(block.get("backoff", STORAGE_SCHEDULER_DEFAULTS["backoff"])),
            "category_weights": dict(
                block.get("category_weights")
                or STORAGE_SCHEDULER_DEFAULTS["category_weights"]
            ),
            "category_max_inflight": dict(
                block.get("category_max_inflight")
                or STORAGE_SCHEDULER_DEFAULTS["category_max_inflight"]
            ),
            "category_default_max_inflight": block.get(
                "category_default_max_inflight",
                STORAGE_SCHEDULER_DEFAULTS["category_default_max_inflight"],
            ),
        }

    @staticmethod
    def _build_governor(generated_at: float) -> dict:
        now_ts = time.time()
        with _connect_redis() as conn:
            # Redis health first — a dead connection raises here and the caller
            # degrades to redis.up=false.
            redis_health = _redis_health(conn)

            lanes, truncated_lanes = _storage_lane_snapshot(conn)
            names = AdminQueuesService._category_name_map()

            # Per-lane stats, grouped for the pool/category rollup.
            lane_stats = {
                lane: _lane_stats(conn, lane, now_ts) for (_, _, _, lane) in lanes
            }

            # --- heavy admission + read-only leak scan --------------------
            effective_max_heavy = None  # resolved from config below
            heavy_members = [
                _decode(m) for m in (conn.smembers(HEAVY_RUNNING_KEY) or [])
            ]
            heavy_members = [m for m in heavy_members if m]

            # Candidate per-category running keys derived FROM the snapshot's
            # (pool, cat) pairs (never a keys('governor:running:*') glob). Every
            # pool with a fair lane also probes the NULL_CATEGORY sentinel (the
            # flat catch-all reserves null-owner jobs there).
            cat_keys = {}  # (pool, category) -> running set key
            for pool, category, tier, _lane in lanes:
                if tier not in _FAIR_TIERS:
                    continue
                if category is not None:
                    cat_keys[(pool, category)] = category_running_key(pool, category)
                cat_keys[(pool, NULL_CATEGORY)] = category_running_key(
                    pool, NULL_CATEGORY
                )

            cat_members = {}  # running key -> [job_id, ...]
            if cat_keys:
                try:
                    with conn.pipeline() as pipe:
                        for key in cat_keys.values():
                            pipe.smembers(key)
                        results = pipe.execute()
                    for key, res in zip(cat_keys.values(), results):
                        cat_members[key] = [
                            m for m in (_decode(x) for x in (res or [])) if m
                        ]
                except Exception:
                    cat_members = {}

            set_members = {HEAVY_RUNNING_KEY: heavy_members}
            set_members.update(cat_members)
            leaks, truncated_inflight = _leak_scan(conn, set_members)

            # --- effective config + mirror diff ---------------------------
            block = {}
            raw = None  # bound before the try so a failing GET (redis up, one key
            # unreadable) degrades only config_mirrored, not the whole gauge.
            try:
                raw = conn.get(GOVERNOR_CONFIG_KEY)  # READ ONLY (no re-publish)
                if raw:
                    block = json.loads(raw)
                    if not isinstance(block, dict):
                        block = {}
            except Exception:
                block = {}
            effective = AdminQueuesService._effective_config(block)
            effective_max_heavy = effective["max_heavy"]
            try:
                db_block = Config.get_storage_scheduler_config() or {}
                config_mirrored = bool(raw) and (block == db_block)
            except Exception:
                config_mirrored = bool(raw)

            # --- worker health + multitenancy flag ------------------------
            worker_rows, multitenancy_active = AdminQueuesService._worker_health_rows(
                conn
            )

        # ----- assemble pools / categories (out of the Redis context) -----
        heavy_scard = leaks.get(HEAVY_RUNNING_KEY, {}).get("count", len(heavy_members))
        heavy_leaked = leaks.get(HEAVY_RUNNING_KEY, {}).get("leaked", 0)
        heavy = {
            "running": heavy_scard,
            "cap": effective_max_heavy,
            "at_cap": (
                heavy_scard >= effective_max_heavy if effective_max_heavy else False
            ),
            "leaked": heavy_leaked,
        }

        weights = effective.get("category_weights") or {}
        caps = effective.get("category_max_inflight") or {}
        default_cap = effective.get("category_default_max_inflight")

        # Coverage: (pool, tier) served by any live worker (best-effort — degrades
        # to 'unknown' when a worker's served set is not known).
        covered_pairs, coverage_known = AdminQueuesService._served_coverage(worker_rows)

        pools = {}
        for pool, category, tier, lane in lanes:
            stats = lane_stats.get(lane, {})
            pg = pools.setdefault(
                pool,
                {
                    "pool": pool,
                    "backlog": {},
                    "oldest_queued_age_seconds": {},
                    "started_over_timeout": {},
                    "failed": {},
                    "_cat": {},
                },
            )
            q = stats.get("queued", 0) or 0
            if q:
                pg["backlog"][tier] = pg["backlog"].get(tier, 0) + q
            age = stats.get("oldest_queued_age_seconds")
            if age is not None:
                prev = pg["oldest_queued_age_seconds"].get(tier)
                pg["oldest_queued_age_seconds"][tier] = (
                    age if prev is None else max(prev, age)
                )
            sot = stats.get("started_over_timeout", 0) or 0
            if sot:
                pg["started_over_timeout"][tier] = (
                    pg["started_over_timeout"].get(tier, 0) + sot
                )
            f = stats.get("failed", 0) or 0
            if f:
                pg["failed"][tier] = pg["failed"].get(tier, 0) + f

            # Fair-tier per-category rollup (bulk/maintenance only).
            if tier in _FAIR_TIERS:
                cat_id = category if category is not None else NULL_CATEGORY
                cg = pg["_cat"].setdefault(
                    cat_id,
                    {
                        "category_id": cat_id,
                        "category_name": AdminQueuesService._resolve_category_name(
                            category, names
                        ),
                        "backlog": {},
                        "oldest_queued_age_seconds": {},
                        "failed": {},
                    },
                )
                if q:
                    cg["backlog"][tier] = cg["backlog"].get(tier, 0) + q
                if age is not None:
                    prev = cg["oldest_queued_age_seconds"].get(tier)
                    cg["oldest_queued_age_seconds"][tier] = (
                        age if prev is None else max(prev, age)
                    )
                if f:
                    cg["failed"][tier] = cg["failed"].get(tier, 0) + f

        # Fold per-category inflight/cap/leak from the running sets into pools.
        warnings = []
        for (pool, category), key in cat_keys.items():
            pg = pools.get(pool)
            if pg is None:
                continue
            cg = pg["_cat"].setdefault(
                category,
                {
                    "category_id": category,
                    "category_name": AdminQueuesService._resolve_category_name(
                        None if category == NULL_CATEGORY else category, names
                    ),
                    "backlog": {},
                    "oldest_queued_age_seconds": {},
                    "failed": {},
                },
            )
            leak_info = leaks.get(key, {})
            inflight = leak_info.get("count", 0)
            leaked = leak_info.get("leaked", 0)
            cap = caps.get(category, default_cap)
            backlog_total = sum(cg.get("backlog", {}).values())
            starved = inflight == 0 and backlog_total > 0
            cg["inflight"] = inflight
            cg["cap"] = cap
            cg["at_cap"] = cap is not None and inflight >= cap
            cg["weight"] = int(weights.get(category, 1))
            cg["leaked"] = leaked
            cg["starved"] = starved
            if leaked > 0:
                warnings.append(
                    {
                        "kind": "leaked_inflight",
                        "scope": "category",
                        "pool": pool,
                        "category_id": category,
                        "counted": inflight,
                        "live": leak_info.get("live", 0),
                    }
                )
            if starved:
                warnings.append(
                    {
                        "kind": "category_starved",
                        "pool": pool,
                        "category_id": category,
                    }
                )

        if heavy_leaked > 0:
            warnings.append(
                {
                    "kind": "leaked_inflight",
                    "scope": "heavy",
                    "counted": heavy_scard,
                    "live": leaks.get(HEAVY_RUNNING_KEY, {}).get("live", 0),
                }
            )

        # Stranded lanes: backlog with no live consumer (only when coverage known).
        for pool, category, tier, lane in lanes:
            stats = lane_stats.get(lane, {})
            if not (stats.get("queued", 0) or 0):
                continue
            pair = (pool, tier)
            if not coverage_known.get(pair, False):
                continue  # suppress rather than false-fire (rolling upgrade)
            if pair not in covered_pairs:
                warnings.append(
                    {
                        "kind": "stranded_lane",
                        "pool": pool,
                        "tier": tier,
                        "lane": lane,
                        "backlog": stats.get("queued", 0),
                        "coverage_known": True,
                    }
                )

        # --- always surface the install's configured categories ------------
        # Categories above are discovered from live rq:queues lanes + running
        # sets, which are GC'd/expire when idle -> on a per-category (P2) install
        # with no active bulk/maintenance work the per-category fairness panels
        # would read "No data". Seed the configured categories (always at least
        # "default") with a zero baseline on every fair-scheduling pool so those
        # panels always render the install's categories. Gated on P2 being
        # actually active: a flat/P1 install has no per-category scheduling, so
        # its per-category panels stay legitimately empty. setdefault never
        # clobbers a category already folded in from live inflight above.
        if multitenancy_active is True:
            seed_categories = sorted(set(weights) | set(caps) | {"default"})
            fair_pools = {
                row["pool"] for row in worker_rows if row.get("up") and row.get("pool")
            } | set(pools.keys())
            for pool in fair_pools:
                pg = pools.setdefault(
                    pool,
                    {
                        "pool": pool,
                        "backlog": {},
                        "oldest_queued_age_seconds": {},
                        "started_over_timeout": {},
                        "failed": {},
                        "_cat": {},
                    },
                )
                for cat in seed_categories:
                    pg["_cat"].setdefault(
                        cat,
                        {
                            "category_id": cat,
                            "category_name": AdminQueuesService._resolve_category_name(
                                None if cat == NULL_CATEGORY else cat, names
                            ),
                            "backlog": {},
                            "oldest_queued_age_seconds": {},
                            "failed": {},
                            "inflight": 0,
                            "cap": caps.get(cat, default_cap),
                            "weight": int(weights.get(cat, 1)),
                            "at_cap": False,
                            "leaked": 0,
                            "starved": False,
                        },
                    )

        pool_list = []
        for pg in pools.values():
            cats = list(pg.pop("_cat").values())
            for cg in cats:
                cg.setdefault("inflight", 0)
                cg.setdefault("cap", None)
                cg.setdefault("at_cap", False)
                cg.setdefault("weight", 1)
                cg.setdefault("leaked", 0)
                cg.setdefault("starved", False)
            pg["categories"] = sorted(cats, key=lambda c: c["category_id"])
            pool_list.append(pg)
        pool_list.sort(key=lambda p: p["pool"])

        return {
            "generated_at": generated_at,
            "data_age_seconds": max(0.0, time.time() - generated_at),
            "multitenancy_active": multitenancy_active,
            "config_enabled": effective["enabled"],
            "config_mirrored": config_mirrored,
            "psi_limit": effective["psi_limit"],
            "redis": redis_health,
            "heavy": heavy,
            "pools": pool_list,
            "workers": worker_rows,
            "warnings": warnings,
            "truncated_lanes": truncated_lanes,
            "truncated_inflight": truncated_inflight,
            "config": effective,
        }

    @staticmethod
    def _served_coverage(worker_rows: list) -> tuple:
        """(pool, tier) pairs served by a live worker, and whether coverage for a
        pair is KNOWN (a live worker with a known served set covers it; a live
        worker whose served set is unknown makes its birth pools' coverage
        unknown -> StrandedLane is suppressed for those, never false-fired)."""
        covered = set()
        known = {}
        for row in worker_rows:
            if not row.get("up"):
                continue
            for lane in row.get("served_lanes") or []:
                parsed = parse_storage_queue(lane)
                if parsed:
                    pair = (parsed[0], parsed[2])
                    covered.add(pair)
                    known[pair] = True
            if not row.get("served_known"):
                # This live worker might serve a lane we cannot see; mark its
                # pool/tier coverage unknown unless another worker proves it.
                for lane in row.get("served_lanes") or []:
                    parsed = parse_storage_queue(lane)
                    if parsed:
                        pair = (parsed[0], parsed[2])
                        known.setdefault(pair, False)
        return covered, known

    @staticmethod
    @cached(backlog_cache)
    def get_backlog_rollup() -> list:
        """Per-``(pool, category, tier)`` backlog rollup (P2.4 §2.4): queued /
        started / started-over-timeout / failed / deferred + head-only
        oldest-queued-age + has_consumer / coverage_known / stranded + category
        name. Bare list. Degrades to ``[]`` on transient Redis failure."""
        try:
            return AdminQueuesService._build_backlog_rollup()
        except Error:
            raise
        except Exception:
            return []

    @staticmethod
    def _build_backlog_rollup() -> list:
        now_ts = time.time()
        with _connect_redis() as conn:
            lanes, _truncated = _storage_lane_snapshot(conn)
            names = AdminQueuesService._category_name_map()
            lane_stats = {
                lane: _lane_stats(conn, lane, now_ts) for (_, _, _, lane) in lanes
            }
            worker_rows, _mt = AdminQueuesService._worker_health_rows(conn)
        covered_pairs, coverage_known = AdminQueuesService._served_coverage(worker_rows)

        rows = []
        for pool, category, tier, lane in lanes:
            stats = lane_stats.get(lane, {})
            pair = (pool, tier)
            has_consumer = pair in covered_pairs
            cov_known = coverage_known.get(pair, False)
            queued = stats.get("queued", 0) or 0
            stranded = bool(queued and cov_known and not has_consumer)
            rows.append(
                {
                    "pool": pool,
                    "category_id": category,
                    "category_name": AdminQueuesService._resolve_category_name(
                        category, names
                    ),
                    "tier": tier,
                    "queued": queued,
                    "started": stats.get("started", 0),
                    "started_over_timeout": stats.get("started_over_timeout", 0),
                    "failed": stats.get("failed", 0),
                    "deferred": stats.get("deferred", 0),
                    "oldest_queued_age_seconds": stats.get("oldest_queued_age_seconds"),
                    "has_consumer": has_consumer,
                    "coverage_known": cov_known,
                    "stranded": stranded,
                }
            )
        rows.sort(
            key=lambda r: (r.get("oldest_queued_age_seconds") or 0, r.get("queued", 0)),
            reverse=True,
        )
        return rows

    @staticmethod
    @cached(problem_tasks_cache)
    def list_problem_tasks(
        kind: str,
        pool: Optional[str],
        category_id: Optional[str],
        tier: Optional[str],
        limit: int,
        offset: int,
    ) -> dict:
        """Bounded, filterable problem-task listing (P2.4 §2.4).

        ``kind`` selects the problem class: ``failed`` (failed_job_registry,
        retryable), ``stuck_running`` (started jobs past their timeout —
        cancelable, composite ids parsed), ``deferred_orphan`` (deferred jobs
        whose chain has settled, ``pending==False``), or ``all`` (union of the
        three, deduped by id).

        Every enumeration is bounded: only lanes from the one ``rq:queues``
        snapshot (filtered by ``pool``/``category_id``/``tier``), each lane's
        relevant registry read only up to ``offset+limit`` ids with
        ``cleanup=False`` (a ``StartedJobRegistry`` cleanup read is a WRITE), and
        an overall ``MAX_PROBLEM_SCAN`` cap. Jobs are materialised through the
        dangling-safe :meth:`Task._tasks_from_source_ids` so a job hash evicted
        mid-listing is skipped instead of aborting the whole page. Degrades to
        200 + an empty page on transient Redis/rdb failure — a polled 500 would
        eject the operator mid-incident."""
        generated_at = time.time()
        try:
            return AdminQueuesService._build_problem_tasks(
                kind, pool, category_id, tier, limit, offset, generated_at
            )
        except Error:
            raise
        except Exception:
            return {
                "generated_at": generated_at,
                "truncated": False,
                "count": 0,
                "tasks": [],
            }

    @staticmethod
    def _build_problem_tasks(
        kind: str,
        pool: Optional[str],
        category_id: Optional[str],
        tier: Optional[str],
        limit: int,
        offset: int,
        generated_at: float,
    ) -> dict:
        now_ts = time.time()
        per_lane_cap = offset + limit  # >=1 (offset>=0, limit>=1)
        kinds = list(_PROBLEM_KINDS) if kind == "all" else [kind]

        truncated = False
        scanned = 0
        seen_ids = set()
        tasks_out = []

        with _connect_redis() as conn:
            lanes, _trunc = _storage_lane_snapshot(conn)
            names = AdminQueuesService._category_name_map()

            # Filter the snapshot lanes to the requested pool / category / tier.
            # A ``category_id`` filter matches the lane's category; a flat lane
            # (None) is unmatched unless ``category_id`` is None (no filter).
            target_lanes = []
            for lpool, lcat, ltier, lane in lanes:
                if pool is not None and lpool != pool:
                    continue
                if tier is not None and ltier != tier:
                    continue
                if category_id is not None and lcat != category_id:
                    continue
                target_lanes.append(lane)

            for lane in target_lanes:
                queue = Queue(lane, connection=conn)
                for k in kinds:
                    if scanned >= MAX_PROBLEM_SCAN:
                        truncated = True
                        break
                    cap = min(per_lane_cap, MAX_PROBLEM_SCAN - scanned)
                    registry, retryable, cancelable, is_started = (
                        _problem_kind_registry(queue, k)
                    )
                    try:
                        # cleanup=False: a StartedJobRegistry cleanup read MOVES
                        # timed-out jobs to FailedJobRegistry (a WRITE).
                        raw_ids = registry.get_job_ids(0, cap - 1, cleanup=False)
                    except Exception:
                        raw_ids = []
                    scanned += len(raw_ids)
                    if len(raw_ids) >= per_lane_cap:
                        truncated = True  # lane hit its per-lane scan cap
                    # StartedJobRegistry members are composite ``{id}:{exec}``.
                    job_ids = (
                        [parse_job_id(i) for i in raw_ids]
                        if is_started
                        else list(raw_ids)
                    )
                    materialized = Task._tasks_from_source_ids(job_ids, registry)
                    for task in materialized:
                        row = AdminQueuesService._problem_task_row(
                            task, k, retryable, cancelable, names, now_ts
                        )
                        if row is None:
                            continue
                        if row["id"] in seen_ids:
                            continue
                        seen_ids.add(row["id"])
                        tasks_out.append(row)

        tasks_out.sort(key=lambda t: (t.get("age_seconds") or 0.0), reverse=True)
        if len(tasks_out) > per_lane_cap:
            truncated = True  # merged pre-slice count exceeded the window
        page = tasks_out[offset : offset + limit]
        return {
            "generated_at": generated_at,
            "truncated": truncated,
            "count": len(page),
            "tasks": page,
        }

    @staticmethod
    def _problem_task_row(
        task, kind: str, retryable: bool, cancelable: bool, names: dict, now_ts: float
    ) -> Optional[dict]:
        """Build one ``ProblemTask`` dict from a materialised ``Task``, applying
        the kind-specific keep/skip filter. Returns ``None`` to skip the task
        (over-timeout miss for ``stuck_running``, or a still-pending deferred
        job for ``deferred_orphan``). Best-effort — a job that vanished
        mid-build returns ``None`` rather than aborting the page."""
        try:
            job = task.job

            pending = None
            if kind == "stuck_running":
                # Keep only jobs OVER their timeout (holds a slot forever).
                if job.started_at is None or not job.timeout:
                    return None
                if not (job.started_at.timestamp() + (job.timeout or 0) < now_ts):
                    return None
            elif kind == "deferred_orphan":
                # Keep only orphans: a DEFERRED job whose chain has all settled
                # (pending==False) was never re-enqueued and is stuck forever.
                pending = task.pending
                if pending is not False:
                    return None

            enqueued_at = _dt_to_ts(job.enqueued_at)
            started_at = _dt_to_ts(job.started_at)
            ended_at = _dt_to_ts(job.ended_at)
            # age: from the most-relevant timestamp for the kind.
            base = started_at if kind == "stuck_running" else enqueued_at
            age_seconds = max(0.0, now_ts - base) if base is not None else None

            if pending is None:
                try:
                    pending = task.pending
                except Exception:
                    pending = None

            category_id = task.category_id
            parsed = parse_storage_queue(task.queue) if task.queue else None
            return {
                "id": task.id,
                "kind": kind,
                "action": task.task,
                "queue": task.queue,
                "pool": parsed[0] if parsed else None,
                "category_id": category_id,
                "category_name": AdminQueuesService._resolve_category_name(
                    category_id, names
                ),
                "tier": parsed[2] if parsed else None,
                "job_status": task.job_status,
                "pending": pending,
                "retries_left": getattr(job, "retries_left", None),
                "enqueued_at": enqueued_at,
                "started_at": started_at,
                "ended_at": ended_at,
                "age_seconds": age_seconds,
                "exc_string": _job_exc_string(job),
                "retryable": retryable,
                "cancelable": cancelable,
            }
        except Exception:
            return None

    @staticmethod
    def get_old_tasks(older_than: int) -> list:
        """Get old task keys."""
        return AdminQueuesService._get_old_jobs(older_than)

    @staticmethod
    def _get_all_queue_job_ids(
        queue_name: str, registries: Optional[list[str]] = None
    ) -> list[str]:
        if registries is None:
            registries = QUEUE_REGISTRIES
        with _connect_redis() as redis_conn:
            queue = Queue(queue_name, connection=redis_conn)
        registry_mapping = {
            "queued": queue,
            "started": queue.started_job_registry,
            "finished": queue.finished_job_registry,
            "failed": queue.failed_job_registry,
            "deferred": queue.deferred_job_registry,
            "scheduled": queue.scheduled_job_registry,
            "canceled": queue.canceled_job_registry,
        }
        registry_objects = [registry_mapping[reg] for reg in registries]
        job_ids = []
        for registry in registry_objects:
            job_ids.extend(registry.get_job_ids())
        return job_ids

    @staticmethod
    def _get_old_jobs(
        older_than: int,
        batch_size: int = 5000,
        rtype: str = "key",
        registries: Optional[list[str]] = None,
    ) -> list:
        if registries is None:
            registries = ["finished"]
        for reg in registries:
            if reg not in QUEUE_REGISTRIES:
                raise Error(
                    "bad_request",
                    f"Invalid registry: {reg}. Valid registries are: {QUEUE_REGISTRIES}",
                )
            if reg in ["queued", "started", "scheduled"]:
                raise Error(
                    "bad_request",
                    f"Registry {reg} is not valid for this operation.",
                )
        time_cutoff = time.time() - older_than
        with _connect_redis() as redis_conn:
            queues = Queue.all(connection=redis_conn)
        finished_jobs = []
        for q in queues:
            finished_jobs.extend(
                AdminQueuesService._get_all_queue_job_ids(q.name, registries)
            )
        old_keys = []
        for i in range(0, len(finished_jobs), batch_size):
            batch_ids = finished_jobs[i : i + batch_size]
            with _connect_redis() as redis_conn:
                jobs = Job.fetch_many(batch_ids, connection=redis_conn)
            for job in jobs:
                if job is None:
                    continue
                if job.ended_at is None or job.ended_at.timestamp() < time_cutoff:
                    if rtype == "key":
                        old_keys.append(job.key.decode())
                    elif rtype == "id":
                        old_keys.append(job.id)
                    elif rtype == "job":
                        old_keys.append(job)
        return old_keys

    @staticmethod
    def _delete_jobs(jobs: list) -> tuple[list[str], list[str]]:
        ok = []
        errors = []
        for job in jobs:
            try:
                job.delete(delete_dependents=True)
            except Exception:
                errors.append(job.id)
            else:
                ok.append(job.id)
        return ok, errors

    @staticmethod
    def delete_old_tasks(older_than: int) -> dict:
        """Delete old tasks older than given seconds."""
        old_jobs = AdminQueuesService._get_old_jobs(older_than, rtype="job")
        delete_ok, delete_errors = AdminQueuesService._delete_jobs(old_jobs)
        clear_queue_data_caches()
        return {"ok": delete_ok, "errors": delete_errors}

    @staticmethod
    def set_max_time(max_time: int) -> dict:
        """Set auto delete max time config."""
        max_time = 86400 if int(max_time) < 86400 else int(max_time)
        AdminQueuesService._set_auto_delete_enabled(True)
        Config.update_old_tasks({"older_than": max_time})
        return {"older_than": max_time}

    @staticmethod
    def _set_auto_delete_enabled(enabled: bool) -> None:
        Config.update_old_tasks({"enabled": enabled})

    @staticmethod
    def set_queue_registries(queue_registries: list) -> dict:
        """Set auto delete queue registries config."""
        for reg in queue_registries:
            if reg not in QUEUE_REGISTRIES:
                raise Error(
                    "bad_request",
                    f"Invalid registry: {reg}. Valid registries are: {QUEUE_REGISTRIES}",
                )
        Config.update_old_tasks({"queue_registries": queue_registries})
        return {"queue_registries": queue_registries}

    @staticmethod
    def set_auto_delete_enabled(enabled: bool) -> dict:
        """Set auto delete enabled/disabled."""
        AdminQueuesService._set_auto_delete_enabled(enabled)
        return {"enabled": enabled}

    @staticmethod
    def get_auto_delete_config() -> dict:
        """Get auto delete configuration."""
        kwargs = Config.get_old_tasks_config()
        return {
            "older_than": kwargs.get("older_than", None),
            "queue_registries": kwargs.get("queue_registries", []),
            "enabled": kwargs.get("enabled", False),
        }

    @staticmethod
    def _publish_governor_config(block: dict) -> None:
        """Mirror the raw storage-governor block into the shared RQ Redis
        (``governor:config``) so the elastic storage workers — which never open
        a RethinkDB connection and may run on a different host from isard-db —
        read their live config from a channel they already use. The RAW block is
        published (only the keys an admin actually set), so the worker's
        per-key DB->env->hardcoded merge still falls an unset key back to env.

        Best-effort: a Redis blip must not fail the admin write; the next
        GET/PUT re-publishes and the worker keeps its env/hardcoded values in
        the meantime."""
        try:
            with _connect_redis() as redis_conn:
                redis_conn.set(GOVERNOR_CONFIG_KEY, json.dumps(block or {}))
        except Exception:
            pass

    @staticmethod
    def get_storage_scheduler_config() -> dict:
        """Get the live storage-governor config, presentation-defaulted.

        Returns the effective values an admin sees for the DB block over the
        deployment defaults, and re-publishes the raw block to the workers'
        Redis mirror (so a viewed page also resynchronises the mirror after a
        Redis restart). The elastic storage workers do their own
        DB->env->hardcoded merge each poll, so these defaults only fill in the
        admin view of an unset block."""
        block = Config.get_storage_scheduler_config()
        AdminQueuesService._publish_governor_config(block)

        def _defaulted(key: str):
            # A present-but-None value (a partial or legacy config block) must
            # fall back to the deployment default rather than crash the numeric
            # casts below: dict.get(key, default) returns None when the key
            # exists with a None value, so guard on None explicitly.
            value = block.get(key)
            return STORAGE_SCHEDULER_DEFAULTS[key] if value is None else value

        return {
            "enabled": bool(_defaulted("enabled")),
            "psi_limit": float(_defaulted("psi_limit")),
            "max_heavy": int(_defaulted("max_heavy")),
            "backoff": int(_defaulted("backoff")),
            "category_weights": dict(
                block.get("category_weights")
                or STORAGE_SCHEDULER_DEFAULTS["category_weights"]
            ),
            "category_max_inflight": dict(
                block.get("category_max_inflight")
                or STORAGE_SCHEDULER_DEFAULTS["category_max_inflight"]
            ),
            "category_default_max_inflight": block.get(
                "category_default_max_inflight",
                STORAGE_SCHEDULER_DEFAULTS["category_default_max_inflight"],
            ),
        }

    @staticmethod
    def set_storage_scheduler_config(updates: dict) -> dict:
        """Persist a partial storage-governor config with bounds, then mirror it
        to the workers' Redis (via the returning get).

        Only the supplied keys are written (siblings preserved). An
        out-of-range or wrong-type value is rejected (400) rather than bricking
        the workers, and numeric knobs are clamped to safe ranges — psi_limit to
        0..100, the cap and poll to >=1 (a 0 would wedge the worker). The
        returning ``get_storage_scheduler_config`` re-publishes the fresh raw
        block to ``governor:config`` so the elastic workers pick it up next poll
        without any RethinkDB connection of their own."""
        clean = {}
        if updates.get("enabled") is not None:
            if not isinstance(updates["enabled"], bool):
                raise Error("bad_request", "enabled must be a boolean")
            clean["enabled"] = updates["enabled"]
        if updates.get("psi_limit") is not None:
            try:
                value = float(updates["psi_limit"])
            except (TypeError, ValueError):
                raise Error("bad_request", "psi_limit must be a number")
            clean["psi_limit"] = min(100.0, max(0.0, value))
        if updates.get("max_heavy") is not None:
            try:
                value = int(updates["max_heavy"])
            except (TypeError, ValueError):
                raise Error("bad_request", "max_heavy must be an integer")
            clean["max_heavy"] = max(1, min(64, value))
        if updates.get("backoff") is not None:
            try:
                value = int(updates["backoff"])
            except (TypeError, ValueError):
                raise Error("bad_request", "backoff must be an integer")
            # Upper-bounded at 60s: a backoff at/above the worker-status hash TTL
            # (90s) would let every governed worker's hash expire between its own
            # polls, reporting the whole fleet DOWN, and would delay the admin's
            # own corrective config read by that long — unrecoverable from the UI.
            # Review #11.
            clean["backoff"] = max(1, min(60, value))
        # Per-category fairness maps: a supplied map REPLACES the stored one; each
        # value is coerced to an int and floored at 1 (a weight/cap of 0 would
        # silently starve or wedge a category). A non-dict / non-numeric entry is
        # rejected rather than persisted so the workers can't read garbage.
        for mapkey in ("category_weights", "category_max_inflight"):
            if updates.get(mapkey) is not None:
                raw = updates[mapkey]
                if not isinstance(raw, dict):
                    raise Error("bad_request", f"{mapkey} must be an object")
                cleaned_map = {}
                for cat, val in raw.items():
                    try:
                        v = int(val)
                    except (TypeError, ValueError):
                        raise Error(
                            "bad_request", f"{mapkey}[{cat}] must be an integer"
                        )
                    # Upper-bounded at 1000: _weighted_rotation materialises a
                    # [cat]*weight list every poll on every governed worker, so an
                    # unbounded weight is a multi-second stall / OOM vector. A cap
                    # of 1000 is likewise plenty for any real per-category limit.
                    # Review #11.
                    cleaned_map[str(cat)] = max(1, min(1000, v))
                clean[mapkey] = cleaned_map
        if updates.get("category_default_max_inflight") is not None:
            try:
                value = int(updates["category_default_max_inflight"])
            except (TypeError, ValueError):
                raise Error(
                    "bad_request", "category_default_max_inflight must be an integer"
                )
            clean["category_default_max_inflight"] = max(1, min(1000, value))
        if not clean:
            raise Error("bad_request", "No valid storage_scheduler fields provided")
        Config.update_storage_scheduler(clean)
        return AdminQueuesService.get_storage_scheduler_config()

    @staticmethod
    def delete_old_tasks_auto() -> dict:
        """Delete old tasks based on auto-delete config."""
        kwargs = AdminQueuesService.get_auto_delete_config()
        if not kwargs.get("enabled", False):
            return {"ok": [], "errors": []}
        if kwargs.get("older_than") is None:
            raise Error("bad_request", "No max_time set in the db.")
        if kwargs.get("queue_registries") is None:
            raise Error("bad_request", "No queue_registries set in the db.")
        old_jobs = AdminQueuesService._get_old_jobs(
            kwargs["older_than"],
            rtype="job",
            registries=kwargs["queue_registries"],
        )
        delete_ok, delete_errors = AdminQueuesService._delete_jobs(old_jobs)
        clear_queue_data_caches()
        return {"ok": delete_ok, "errors": delete_errors}
