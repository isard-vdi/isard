"""RQ worker with resource-aware admission for heavy storage tasks.

Used by the ELASTIC and TEMPLATE storage pools (docker/storage/init.sh via
``rq worker --worker-class``). Before running a job taken from a HEAVY-tier
queue (``template`` / ``maintenance`` / ``reclaim`` — see
:data:`isardvdi_common.lib.queue_tiers.HEAVY_TIERS`) it consults
:mod:`isardvdi_common.lib.resource_governor`: if the node is under CPU/IO
pressure (PSI) or heavy concurrency is already at its cap, the heavy queues are
dropped from the dequeue this round — so heavy work lands in low-load troughs and
never overloads the node. Non-heavy jobs (bulk throughput / interactive /
standard overflow) are unaffected.

The reserved, standard-lane and bg-floor pools use the stock ``Worker`` (the
bg-floor is intentionally ungoverned so >=1 heavy task always makes progress).

RQ 2.3.2 detail that shapes this code: ``Worker.dequeue_job_and_maintain_ttl``
owns a ``while True`` loop that reads ``dequeue_any(self._ordered_queues, …)``
and, with ``max_idle_time=None`` (the production default), **blocks forever** —
it only ever returns a ``(job, queue)`` tuple, never ``None`` — and ``work()``
treats a ``None`` return as "quit". So we cannot get pressure re-evaluation by
calling ``super()`` with a short timeout (its inner loop would freeze on the
first filtered queue set and never re-check), nor by returning ``None`` (that
kills the worker). Instead we reimplement the dequeue loop here: each poll we
re-evaluate PSI/cap, pick the queue set for that poll (all queues, or the
non-heavy subset), and BLPOP with a short ``gov_backoff`` timeout via
``dequeue_any`` (preserving RQ's reliable-queue / intermediate-queue
semantics). We never return ``None`` while blocking — only when a caller
supplied ``max_idle_time`` budget is exhausted, or on a burst drain.

Heavy concurrency is tracked as a Redis SET of in-flight heavy job ids
(``governor:heavy_running``): the count is ``SCARD``, admission is an atomic
check-and-add Lua script, and release is ``SREM`` in ``execute_job``. Unlike a
bare counter this is self-healing — each reservation is tagged with the owning
worker's name (``governor:reserved_by:<id>``), so a boot/at-cap reconcile prunes
a slot once its job stops being live OR its worker's ``rq:worker`` heartbeat
expires (a SIGKILL/OOM leaves the orphaned job reading ``started``/``queued``
forever, which the status check alone would never reclaim). A leak only ever
*under*-admits (safe), never over-admits.

The knobs (``enabled`` kill-switch, ``psi_limit``, ``max_heavy``, ``backoff``)
are LIVE-tunable from the admin webapp. isard-storage may run on a DIFFERENT
host from isard-db (see ``isardvdi.cfg.example`` FLAVOUR) and must never open a
RethinkDB connection, so this worker does NOT read the config table directly.
Instead apiv4 — which legitimately reaches both stores — mirrors
``config[1].storage_scheduler`` into the shared RQ Redis (key ``governor:config``,
the very Redis this worker already uses as its broker) on every admin edit. Each
dequeue poll the parent reads that key and merges it over the hardcoded startup
defaults (DB -> hardcoded), so an admin can retune pressure/cap or disable gating
without a restart. The read is fault-tolerant: a missing key, a Redis blip or a
bad value falls back per key to the hardcoded default, and — unlike an rdb read —
it needs no fork handling because the Redis client is already RQ-fork-safe.
"""

import json
import os
import time

from isardvdi_common.lib import resource_governor as rg
from isardvdi_common.lib.queue_tiers import (
    _FAIR_TIERS,
    DEFERRABLE_TIERS,
    HEAVY_TIERS,
    NULL_CATEGORY,
    parse_storage_queue,
)
from rq import Worker
from rq.exceptions import DequeueTimeout
from rq.worker import WorkerStatus

# Redis SET of job ids currently holding a heavy slot.
HEAVY_RUNNING_KEY = "governor:heavy_running"

# Redis STRING (JSON) holding the live storage-governor config that apiv4
# mirrors from ``config[1].storage_scheduler``. The worker reads it from the
# shared RQ Redis each poll (never from RethinkDB — see the module docstring).
GOVERNOR_CONFIG_KEY = "governor:config"

# Per-(pool, category) in-flight SET prefix for Phase-2 fair scheduling:
# ``governor:running:<pool>:<category>``. Keyed by POOL (not global) so a shared
# multi-node Redis can't turn a per-category cap into a fleet-wide one.
CATEGORY_RUNNING_PREFIX = "governor:running"


def category_running_key(pool, category):
    return f"{CATEGORY_RUNNING_PREFIX}:{pool}:{category}"


# Per-reservation owner tag: STRING ``governor:reserved_by:<job_id>`` = the name
# of the worker that reserved the slot, TTL-matched to the running set. Lets the
# reconcile prune a slot whose reserving worker has died (#4a/#4b) even while the
# orphaned job's own status still reads ``started``/``queued`` — the signal the
# status-only prune can never catch after a SIGKILL/OOM.
RESERVED_BY_PREFIX = "governor:reserved_by"


def reserved_by_key(job_id):
    return f"{RESERVED_BY_PREFIX}:{job_id}"


# Redis HASH each governed worker publishes once per dequeue poll with its live
# state (PSI, deferring/at-cap, kind, served lanes, structural multitenancy flag,
# and the id+action of the job it most recently began executing). This is the
# ONLY thing the worker writes for observability; the apiv4 storage-governor read
# layer READS these (never writes) to fill in the per-worker health rows and the
# fleet-wide ``multitenancy_active`` flag. Keyed by worker name:
# ``governor:worker:<name>``. Self-expiring (``_WORKER_STATUS_TTL``, comfortably
# above the poll backoff and far below ``_SET_TTL``) so a dead worker's row
# vanishes on its own and the reader treats an absent hash as "worker down".
WORKER_STATUS_PREFIX = "governor:worker"


def worker_status_key(name):
    return f"{WORKER_STATUS_PREFIX}:{name}"


# TTL on the per-worker status hash. A live worker republishes every poll
# (``gov_backoff`` seconds), refreshing this; only a worker that stops polling
# lets it expire, at which point the reader stops counting the worker as live.
_WORKER_STATUS_TTL = 90


# Backstop TTL on the set (refreshed on every reservation). Must exceed the
# longest heavy job (whole-disk ``move`` can run ~12h) so a legitimately held
# slot never expires under a live job; the reconcile below is what actually
# clears leaks, this is only the all-workers-dead safety net.
_SET_TTL = 86400  # 24h

# Atomic admission: add ARGV[1] (job id) to the heavy set iff it currently holds
# fewer than ARGV[2] (max_heavy) members; refresh the TTL. Returns 1 if the slot
# was reserved, 0 if already at the cap. Doing the check-and-add in one Lua call
# closes the check->take race where several workers admit past the cap at once.
_RESERVE_LUA = """
local n = redis.call('SCARD', KEYS[1])
if n < tonumber(ARGV[2]) then
  redis.call('SADD', KEYS[1], ARGV[1])
  redis.call('EXPIRE', KEYS[1], ARGV[3])
  return 1
end
return 0
"""

# Phase-2 fair admission: reserve a per-category slot and (for background) the
# global heavy slot in ONE atomic step — both checks pass before either commits,
# so a partial reservation can never leak. The per-category SADD ALWAYS happens
# (it is the in-flight accounting the weighted-RR ordering reads); the cap is
# only *enforced* when finite (ARGV[2] >= 0), and the global heavy slot is only
# taken for a background job (ARGV[3] == 1).
#   KEYS[1]=category set, KEYS[2]=global heavy set
#   ARGV: [1]=job id, [2]=cat cap (-1 = count only, no cap), [3]=is_background,
#         [4]=max_heavy, [5]=ttl
_FAIR_RESERVE_LUA = """
local catcap = tonumber(ARGV[2])
local isbg = tonumber(ARGV[3])
local maxh = tonumber(ARGV[4])
if catcap >= 0 and redis.call('SCARD', KEYS[1]) >= catcap then return 0 end
if isbg == 1 and redis.call('SCARD', KEYS[2]) >= maxh then return 0 end
redis.call('SADD', KEYS[1], ARGV[1])
redis.call('EXPIRE', KEYS[1], ARGV[5])
if isbg == 1 then
  redis.call('SADD', KEYS[2], ARGV[1])
  redis.call('EXPIRE', KEYS[2], ARGV[5])
end
return 1
"""

# Empty-set GC: delete a per-category running set ONLY if it is still empty at the
# moment of deletion. A plain SCARD==0 then DELETE is a TOCTOU — a concurrent
# _reserve_fair SADD landing between the two round-trips would be silently wiped,
# corrupting the in-flight count and over-admitting past the cap. Doing the check
# and the delete in one Lua step closes that window (the set also self-expires via
# _SET_TTL, so a skipped delete is only a delayed GC, never a correctness issue).
#   KEYS[1]=category set
_GC_EMPTY_LUA = """
if redis.call('SCARD', KEYS[1]) == 0 then return redis.call('DEL', KEYS[1]) end
return 0
"""

# Lane GC: SREM a fully-drained per-category lane from ``rq:queues`` so
# discovery / BLPOP / the admin view don't scan an unbounded set. Registry-aware:
# only when the queue list AND the started/deferred/scheduled registries are all
# empty — else a stranded ``StartedJobRegistry`` job (the one ``clean_registries``
# rescues, #5) would become undiscoverable, or a deferred/scheduled job would be
# lost. One atomic Lua so it can't race RQ's enqueue, which SADDs ``rq:queues``
# then pushes the job inside a MULTI/EXEC pipeline (redis-py default) — atomic vs
# atomic, so we never SREM a lane mid-enqueue.
#   KEYS[1]=rq:queues, KEYS[2]=rq:queue:<name>, KEYS[3]=rq:wip:<name>,
#   KEYS[4]=rq:deferred:<name>, KEYS[5]=rq:scheduled:<name>; ARGV[1]=member
_GC_LANE_LUA = """
if redis.call('LLEN', KEYS[2]) == 0
   and redis.call('ZCARD', KEYS[3]) == 0
   and redis.call('ZCARD', KEYS[4]) == 0
   and redis.call('ZCARD', KEYS[5]) == 0 then
  return redis.call('SREM', KEYS[1], ARGV[1])
end
return 0
"""

# Job statuses that still legitimately hold a heavy slot; anything else in the
# set is stale (finished/failed/canceled/gone — e.g. a SIGKILL'd worker) and is
# pruned by the reconcile.
_LIVE_STATUSES = frozenset({"started", "queued", "deferred", "scheduled"})


def _as_bool(value, default):
    """Coerce a config value to bool, falling back to ``default`` if unusable."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in ("1", "true", "yes", "on")
    return default


def _as_float(value, default):
    """Coerce to a non-negative float; ``default`` on garbage/negative."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return default
    return v if v >= 0 else default


def _as_int(value, default):
    """Coerce to an int >= 1; ``default`` on garbage/out-of-range (a cap or
    poll of 0 would wedge the worker, so the floor is 1)."""
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return v if v >= 1 else default


def _as_opt_int(value, default):
    """Coerce to an int >= 1, or ``None`` (explicitly uncapped). A
    missing/garbage value falls back to ``default`` (which may itself be None)."""
    if value is None:
        return default
    try:
        v = int(value)
    except (TypeError, ValueError):
        return default
    return v if v >= 1 else default


def _as_int_map(value):
    """Coerce a ``{category_id: int>=1}`` mapping, dropping non-str keys and
    non-positive/garbage values. A non-dict becomes ``{}``."""
    if not isinstance(value, dict):
        return {}
    out = {}
    for k, v in value.items():
        if not isinstance(k, str):
            continue
        try:
            iv = int(v)
        except (TypeError, ValueError):
            continue
        if iv >= 1:
            out[k] = iv
    return out


def _merge_live_config(block, env):
    """Pure DB->env merge for the governor knobs. ``block`` is the raw
    ``config[1].storage_scheduler`` dict (possibly empty or holding bad values);
    ``env`` is the env/hardcoded fallback dict. Each key falls back
    independently, so a single bad DB value can't disable the whole governor."""
    block = block or {}
    return {
        "enabled": _as_bool(block.get("enabled"), env["enabled"]),
        "psi_limit": _as_float(block.get("psi_limit"), env["psi_limit"]),
        "max_heavy": _as_int(block.get("max_heavy"), env["max_heavy"]),
        "backoff": _as_int(block.get("backoff"), env["backoff"]),
        # Phase-2 per-category fairness TUNING (only meaningful when the
        # STORAGE_QUEUE_MULTITENANCY structural switch is on; the on/off itself is
        # the env var, not a live knob). Weights/caps stay live-tunable.
        "category_weights": _as_int_map(block.get("category_weights")),
        "category_max_inflight": _as_int_map(block.get("category_max_inflight")),
        "category_default_max_inflight": _as_opt_int(
            block.get("category_default_max_inflight"),
            env["category_default_max_inflight"],
        ),
    }


def is_heavy_queue(name):
    """True for a storage queue whose tier is a HEAVY tier (template /
    maintenance) — node-loading work counted against the global max-heavy
    *concurrency cap*. A subset of :func:`is_deferrable_queue`: ``reclaim`` is
    deferred under pressure but NOT capped (trivial deletes), so it is not heavy.

    Parses the tier segment (handles both the flat ``storage.<pool>.<tier>`` and
    per-category ``storage.<pool>.<cat>.<tier>`` shapes), so a non-storage name or
    a non-heavy tier (interactive/standard/bulk/reclaim/legacy) returns False.
    """
    parsed = parse_storage_queue(name)
    return parsed is not None and parsed[2] in HEAVY_TIERS


def is_deferrable_queue(name):
    """True for a storage queue whose tier is PSI-**deferrable** (template /
    maintenance / reclaim) — hidden from the dequeue order under node pressure. A
    superset of :func:`is_heavy_queue`: ``reclaim`` defers (a mass-delete / broom
    storm can add IO on discard-heavy backends) but is not counted against the
    max-heavy cap. Non-storage or non-deferrable tiers (interactive / standard /
    bulk / legacy) return False.
    """
    parsed = parse_storage_queue(name)
    return parsed is not None and parsed[2] in DEFERRABLE_TIERS


class GovernedWorker(Worker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Fallback defaults; the live governor:config DB block overrides per poll.
        self._default_enabled = True
        self._default_psi_limit = 40.0
        self._default_max_heavy = 2
        self._default_backoff = 3
        # Per-category multitenancy: producers thread the owner category into
        # per-category fair lanes and this worker discovers + weighted-RR
        # fair-schedules across them. Always on in production; kept as an instance
        # flag so a flat-queue worker can still be built (e.g. to drain stray
        # lanes) and for the observability status.
        self.multitenancy = True
        # The bg-floor worker runs this class in FLOOR mode: it discovers and
        # serves per-category lanes (so heavy work on them can't starve under
        # multitenancy) but NEVER governs — no PSI defer, no cap, no reservation —
        # so >=1 heavy task always makes progress regardless of the live governor.
        self._floor = _as_bool(os.environ.get("STORAGE_GOVERNOR_FLOOR"), False)
        self._default_category_default_max_inflight = None
        # Effective (live) knobs; start at the defaults, refreshed each poll.
        self.gov_enabled = self._default_enabled
        self.gov_psi_limit = self._default_psi_limit
        self.gov_max_heavy = self._default_max_heavy
        self.gov_backoff = self._default_backoff
        self.gov_category_weights = {}
        self.gov_category_max_inflight = {}
        self.gov_category_default_max_inflight = (
            self._default_category_default_max_inflight
        )
        # Weighted-RR rotation cursor so equal-share categories take turns across
        # polls instead of one always winning the tie.
        self._wrr_cursor = 0
        # Last job this worker BEGAN executing (id + action), stamped in
        # execute_job and published in the status hash each poll. Enables exact
        # poison-job attribution (catalog #4b): a worker repeatedly killed by the
        # same job leaves that job's id/action visible before the hash expires.
        self._last_job_id = None
        self._last_job_action = None
        # Fair-scheduling scaffolding derived once from the static base queue set:
        # the (pool, tier) pairs whose per-category sub-queues we discover, and a
        # name->Queue cache so we don't rebuild Queue objects every poll.
        self._fair_targets = self._derive_fair_targets()
        self._fair_queue_cache = {}
        # PSI paths are overridable (e.g. a differently-mounted /proc, or tests).
        self.gov_cpu_psi_path = os.environ.get(
            "STORAGE_GOVERNOR_CPU_PSI_PATH", rg.CPU_PRESSURE_PATH
        )
        self.gov_io_psi_path = os.environ.get(
            "STORAGE_GOVERNOR_IO_PSI_PATH", rg.IO_PRESSURE_PATH
        )
        self.gov_mem_psi_path = os.environ.get(
            "STORAGE_GOVERNOR_MEM_PSI_PATH", rg.MEMORY_PRESSURE_PATH
        )
        # Clear any heavy-slot / per-category ids this fleet leaked before we
        # (re)started.
        self._reconcile_heavy()
        self._reconcile_categories()

    def _refresh_live_config(self):
        """Refresh the effective governor knobs from the ``governor:config``
        Redis key that apiv4 mirrors from ``config[1].storage_scheduler``,
        overriding the env/hardcoded startup defaults (DB -> env -> hardcoded).
        Runs once per poll in the PARENT. Reads ONLY the shared RQ Redis (never
        RethinkDB), so it holds even when isard-storage runs on a different host
        from isard-db. Any failure — missing key, Redis blip, bad JSON/value —
        falls back per key so an unsupervised worker can never wedge on config."""
        block = {}
        try:
            raw = self.connection.get(GOVERNOR_CONFIG_KEY)
            if raw:
                block = json.loads(raw)
                if not isinstance(block, dict):
                    block = {}
        except Exception:
            block = {}
        eff = _merge_live_config(
            block,
            {
                "enabled": self._default_enabled,
                "psi_limit": self._default_psi_limit,
                "max_heavy": self._default_max_heavy,
                "backoff": self._default_backoff,
                "category_default_max_inflight": self._default_category_default_max_inflight,
            },
        )
        was_enabled = self.gov_enabled
        self.gov_enabled = eff["enabled"]
        self.gov_psi_limit = eff["psi_limit"]
        self.gov_max_heavy = eff["max_heavy"]
        self.gov_backoff = eff["backoff"]
        self.gov_category_weights = eff["category_weights"]
        self.gov_category_max_inflight = eff["category_max_inflight"]
        self.gov_category_default_max_inflight = eff["category_default_max_inflight"]
        # Kill-switch re-enable: while disabled, heavy jobs ran WITHOUT reserving a
        # slot, so the counters now under-count them and _reserve would admit
        # max_heavy MORE on top. Seed the counters from the live registries before
        # enforcement resumes. The floor never governs, so it never seeds.
        if eff["enabled"] and not was_enabled and not self._floor:
            self._seed_running_from_registries()

    # --- admission signals --------------------------------------------------
    def _pressure_high(self):
        """True iff CPU, IO or MEMORY PSI is above the limit (independent of the
        cap)."""
        # Read the PSI paths defensively (getattr fallback to the canonical
        # /proc paths): a future helper/test that forgets to set one of these
        # attributes must not raise AttributeError out of the hot admission path
        # and silently disable the whole governor (exactly how the memory-PSI
        # gate's missing test wiring went unnoticed).
        return rg.should_defer_heavy(
            cpu_psi=rg.read_pressure(
                getattr(self, "gov_cpu_psi_path", rg.CPU_PRESSURE_PATH)
            ),
            io_psi=rg.read_pressure(
                getattr(self, "gov_io_psi_path", rg.IO_PRESSURE_PATH)
            ),
            mem_psi=rg.read_pressure(
                getattr(self, "gov_mem_psi_path", rg.MEMORY_PRESSURE_PATH)
            ),
            running_heavy=0,
            psi_limit=self.gov_psi_limit,
            max_heavy=10**9,  # disable the cap branch; test PSI only
        )

    def _heavy_at_cap(self):
        try:
            return self.connection.scard(HEAVY_RUNNING_KEY) >= self.gov_max_heavy
        except Exception:
            return False

    def _reserve_heavy(self, job_id):
        """Atomically claim a heavy slot for ``job_id``; True iff under the cap."""
        try:
            ok = bool(
                self.connection.eval(
                    _RESERVE_LUA,
                    1,
                    HEAVY_RUNNING_KEY,
                    job_id,
                    self.gov_max_heavy,
                    _SET_TTL,
                )
            )
        except Exception:
            # never let a Redis hiccup wedge the worker; fail open (admit).
            return True
        if ok:
            self._record_reservation_owner(job_id)
        return ok

    def _release_heavy(self, job_id):
        try:
            self.connection.srem(HEAVY_RUNNING_KEY, job_id)
            self.connection.delete(reserved_by_key(job_id))
        except Exception:
            pass

    def _record_reservation_owner(self, job_id):
        """Tag a fresh reservation with THIS worker's name so the reconcile can
        prune it when the worker dies (#4a/#4b) — a SIGKILL/OOM leaves the
        orphaned job's status reading ``started``/``queued`` forever, so status
        alone never heals it. Best-effort: a missed write just falls back to
        status-only pruning (fail-safe, never over-admits)."""
        try:
            self.connection.set(reserved_by_key(job_id), self.name, ex=_SET_TTL)
        except Exception:
            pass

    def _reservation_owner_alive(self, job_id):
        """True unless we can PROVE the reserving worker is gone (its
        ``rq:worker:<name>`` heartbeat key has expired). Fails OPEN on any
        uncertainty — a missing owner tag (a pre-upgrade reservation, or the tiny
        window before the tag lands) or a Redis error — because a false prune
        would free a slot under a live job and over-admit, which is worse than a
        delayed leak."""
        try:
            owner = self.connection.get(reserved_by_key(job_id))
        except Exception:
            return True
        if not owner:
            return True
        owner = owner.decode() if isinstance(owner, (bytes, bytearray)) else owner
        try:
            return bool(
                self.connection.exists(f"{Worker.redis_worker_namespace_prefix}{owner}")
            )
        except Exception:
            return True

    def _reconcile_heavy(self):
        """Prune ids whose job is no longer running (dead-worker leaks / missed
        release), so a leak can only ever under-admit, not wedge the cap."""
        self._prune_stale_members(HEAVY_RUNNING_KEY)

    def _prune_stale_members(self, key):
        """Drop set members whose job is no longer live (shared by the heavy and
        the per-category reconciles)."""
        try:
            members = self.connection.smembers(key)
        except Exception:
            return
        for m in members or []:
            jid = m.decode() if isinstance(m, (bytes, bytearray)) else m
            try:
                job = self.job_class.fetch(jid, connection=self.connection)
                status = job.get_status(refresh=True)
            except Exception:
                status = None  # job vanished -> stale
            # Stale if the job is no longer live OR the worker that reserved it is
            # gone (#4a/#4b): a SIGKILL/OOM leaves the orphaned job's status
            # reading "started"/"queued" forever, so the status check alone never
            # reclaims the slot — the worker-liveness check does.
            if status not in _LIVE_STATUSES or not self._reservation_owner_alive(jid):
                try:
                    self.connection.srem(key, jid)
                    self.connection.delete(reserved_by_key(jid))
                except Exception:
                    pass

    # --- per-category fair admission (Phase 2) ------------------------------
    def _category_cap(self, category):
        """In-flight cap for a category: its explicit entry, else the default,
        else None (uncapped — the weighted-RR ordering alone provides fairness,
        the per-category counter is still kept for that ordering)."""
        caps = self.gov_category_max_inflight or {}
        if category in caps:
            return caps[category]
        return self.gov_category_default_max_inflight

    def _category_inflight(self, pool, category):
        try:
            return self.connection.scard(category_running_key(pool, category))
        except Exception:
            return 0

    def _category_at_cap(self, pool, category):
        cap = self._category_cap(category)
        if cap is None:
            return False
        if self._category_inflight(pool, category) < cap:
            return False
        # At/above cap: a slot leaked by a dead work-horse would otherwise keep
        # this category out of the dequeue order until the next worker restart
        # (``_reconcile_categories`` runs only at boot) — permanently throttling
        # the tenant. Self-heal just THIS lane and re-check, mirroring the
        # heavy-key reconcile in ``_defer_background``. Bounded: it
        # fires only for a lane already at its cap, exactly like the heavy path.
        self._prune_stale_members(category_running_key(pool, category))
        return self._category_inflight(pool, category) >= cap

    def _reserve_fair(self, job_id, pool, category, is_heavy):
        """Atomically reserve the per-category slot (always counted) and, for a
        heavy job (template/maintenance/reclaim), the global heavy slot —
        both-or-neither. True iff admitted; fails open on a Redis error so a
        hiccup can't wedge the worker."""
        cap = self._category_cap(category)
        try:
            ok = bool(
                self.connection.eval(
                    _FAIR_RESERVE_LUA,
                    2,
                    category_running_key(pool, category),
                    HEAVY_RUNNING_KEY,
                    job_id,
                    -1 if cap is None else int(cap),
                    1 if is_heavy else 0,
                    self.gov_max_heavy,
                    _SET_TTL,
                )
            )
        except Exception:
            return True
        if ok:
            self._record_reservation_owner(job_id)
        return ok

    def _release_fair(self, job_id, pool, category, is_heavy):
        """Release the per-category slot and (for a heavy job) the global heavy
        slot. SREM is idempotent, so releasing a slot we never reserved (e.g.
        fairness toggled between dequeue and execute) is a harmless no-op."""
        try:
            self.connection.srem(category_running_key(pool, category), job_id)
        except Exception:
            pass
        if is_heavy:
            self._release_heavy(job_id)  # also clears the owner tag
        else:
            try:
                self.connection.delete(reserved_by_key(job_id))
            except Exception:
                pass

    def _scan_match(self, pattern):
        """Cursor-based ``SCAN`` for keys matching ``pattern`` (never ``KEYS`` —
        that is O(N) and blocks the single-threaded shared RQ broker, #13).
        Returns an empty iterator on a Redis error."""
        try:
            return self.connection.scan_iter(match=pattern, count=100)
        except Exception:
            return iter(())

    def _reconcile_categories(self):
        """Prune leaked ids from every ``governor:running:<pool>:<category>`` set
        (dead-worker self-heal), delete a running set once it is empty, and GC
        fully-drained per-category lanes from ``rq:queues`` — all via ``SCAN`` /
        ``SMEMBERS``, never ``KEYS``, so the shared broker is never blocked."""
        for key in list(self._scan_match(f"{CATEGORY_RUNNING_PREFIX}:*")):
            k = key.decode() if isinstance(key, (bytes, bytearray)) else key
            self._prune_stale_members(k)
            # Atomic empty-check-then-delete: a plain scard==0 / delete pair would
            # race a concurrent _reserve_fair SADD and wipe a live reservation.
            try:
                self.connection.eval(_GC_EMPTY_LUA, 1, k)
            except Exception:
                pass
        self._gc_drained_category_lanes()

    def _gc_drained_category_lanes(self):
        """SREM fully-drained per-category lanes (this worker's ``_fair_targets``)
        from ``rq:queues`` so the set can't grow without bound as categories come
        and go (#16). Registry-aware via ``_GC_LANE_LUA`` — a lane still holding a
        started/deferred/scheduled job is left in place so it stays discoverable
        for the ``clean_registries`` rescue (#5)."""
        try:
            members = self.connection.smembers("rq:queues")
        except Exception:
            return
        for m in members or []:
            name = m.decode() if isinstance(m, (bytes, bytearray)) else m
            if not name.startswith("rq:queue:"):
                continue
            qname = name[len("rq:queue:") :]
            parsed = parse_storage_queue(qname)
            if not parsed or parsed[1] is None:
                continue  # only per-category lanes (a category segment present)
            pool, _category, tier = parsed
            if (pool, tier) not in self._fair_targets:
                continue
            try:
                self.connection.eval(
                    _GC_LANE_LUA,
                    5,
                    "rq:queues",
                    name,
                    f"rq:wip:{qname}",
                    f"rq:deferred:{qname}",
                    f"rq:scheduled:{qname}",
                    name,
                )
            except Exception:
                pass

    def _seed_running_from_registries(self):
        """Seed the running counters from the heavy/fair lanes' StartedJobRegistry
        on a kill-switch re-enable (#15). Jobs that ran while the governor was off
        held NO reservation, so without this the counters under-count them and
        ``_reserve`` would admit ``max_heavy`` MORE on top. ``SADD`` is idempotent
        (concurrent re-enables across workers can't double-count); a seeded id
        carries no owner tag, so the reconcile reclaims it by status once its job
        finishes."""
        lanes = []  # (started-registry queue name, pool, category-or-None, tier)
        for q in getattr(self, "_ordered_queues", None) or []:
            parsed = parse_storage_queue(q.name)
            if parsed and parsed[1] is None and parsed[2] in _FAIR_TIERS:
                cat = NULL_CATEGORY if self.multitenancy else None
                lanes.append((q.name, parsed[0], cat, parsed[2]))
        for (pool, tier), cats in self._discover_fair_queues().items():
            for c in cats:
                lanes.append((f"storage.{pool}.{c}.{tier}", pool, c, tier))
        for qname, pool, category, tier in lanes:
            try:
                jids = self.connection.zrange(f"rq:wip:{qname}", 0, -1)
            except Exception:
                continue
            for j in jids or []:
                jid = j.decode() if isinstance(j, (bytes, bytearray)) else j
                try:
                    if tier in HEAVY_TIERS:
                        self.connection.sadd(HEAVY_RUNNING_KEY, jid)
                        self.connection.expire(HEAVY_RUNNING_KEY, _SET_TTL)
                    if category is not None:
                        self.connection.sadd(category_running_key(pool, category), jid)
                        self.connection.expire(
                            category_running_key(pool, category), _SET_TTL
                        )
                except Exception:
                    pass

    # --- per-category discovery + weighted-RR ordering (Phase 2) -------------
    def _is_governing(self):
        """The governor actively gates (defers, caps, reserves) only when it is
        enabled AND this is not the ungoverned bg-floor worker."""
        return self.gov_enabled and not self._floor

    def _derive_fair_targets(self):
        """The ``(pool, tier)`` pairs this worker fair-schedules, read ONCE from
        its static base queue set: the flat bulk/background lanes (including the
        cross-pool ``src:dst`` move lanes). Per-category sub-queues are discovered
        only for these, so a worker that serves no bulk/background never scans."""
        targets = set()
        for q in getattr(self, "_ordered_queues", None) or []:
            parsed = parse_storage_queue(q.name)
            if parsed and parsed[1] is None and parsed[2] in _FAIR_TIERS:
                targets.add((parsed[0], parsed[2]))
        return targets

    def _discover_fair_queues(self):
        """SMEMBERS ``rq:queues`` and return ``{(pool, tier): [category, ...]}``
        of the active per-category sub-queues for this worker's fair targets.
        Empty on any Redis error — the flat catch-all still serves everything."""
        if not self._fair_targets:
            return {}
        try:
            members = self.connection.smembers("rq:queues")
        except Exception:
            return {}
        active = {}
        for m in members or []:
            name = m.decode() if isinstance(m, (bytes, bytearray)) else m
            if not name.startswith("rq:queue:"):
                continue
            parsed = parse_storage_queue(name[len("rq:queue:") :])
            if not parsed:
                continue
            pool, category, tier = parsed
            if category is not None and (pool, tier) in self._fair_targets:
                active.setdefault((pool, tier), []).append(category)
        return active

    @staticmethod
    def _weighted_rotation(categories, weights, cursor):
        """Weighted round-robin priority order of ``categories`` for one poll.

        Each category is expanded by its integer weight (default 1), the ring is
        rotated by ``cursor`` so a different category leads each poll, then
        de-duplicated to first occurrence. ``dequeue_any`` takes the first
        non-empty queue, so leading position = pick priority; higher-weight
        categories lead proportionally more often across polls -> weighted share.
        """
        cats = sorted(categories)
        if not cats:
            return []
        expanded = []
        for c in cats:
            expanded.extend([c] * max(1, int((weights or {}).get(c, 1))))
        off = cursor % len(expanded)
        seen, order = set(), []
        for c in expanded[off:] + expanded[:off]:
            if c not in seen:
                seen.add(c)
                order.append(c)
        return order

    def _make_fair_queue(self, name):
        """A cached Queue object for a discovered per-category lane (so we don't
        rebuild Queue objects every poll)."""
        q = self._fair_queue_cache.get(name)
        if q is None:
            q = self.queue_class(
                name,
                connection=self.connection,
                job_class=self.job_class,
                serializer=self.serializer,
            )
            self._fair_queue_cache[name] = q
        return q

    def _discovered_lane_queues(self):
        """Queue objects for this worker's currently-discovered per-category lanes
        — bounded to ``_fair_targets`` (its own pools/tiers). These live in
        ``_ordered_queues`` per poll but never in ``self.queues``, so RQ's
        registry maintenance skips them (see ``clean_registries``)."""
        lanes = []
        for (pool, tier), cats in self._discover_fair_queues().items():
            for c in cats:
                lanes.append(self._make_fair_queue(f"storage.{pool}.{c}.{tier}"))
        return lanes

    def clean_registries(self):
        """Also run RQ's registry maintenance over the discovered per-category
        lanes. RQ's ``clean_registries`` only walks ``self.queues`` (the static
        base set); the per-category lanes are discovered dynamically and never
        added there, so a work-horse OOM/SIGKILL on such a lane would strand its
        ``StartedJobRegistry`` entry forever — no worker ever rescues it (catalog
        #5). Extend the queue set for the duration of the maintenance pass (which
        runs synchronously between polls) so RQ cleans the base AND the category
        lanes with its own per-queue maintenance lock, then restore it before the
        next dequeue so the #1 intermediate-queue length logic is untouched. The
        lanes stay in ``rq:queues`` even when drained, so a stranded-but-empty
        lane is still reached (a registry-aware ``rq:queues`` GC — #16 — must
        preserve that invariant)."""
        extra = self._discovered_lane_queues() if self.multitenancy else []
        if not extra:
            return super().clean_registries()
        original = self.queues
        self.queues = list(original) + extra
        try:
            super().clean_registries()
        finally:
            self.queues = original

    def _ordered_base_for_poll(self):
        """The static base queue set for this poll. For the ungoverned bg-floor —
        the SOLE heavy drainer once every governed pool is deferring under
        sustained pressure — rotate the lanes by the per-poll cursor so the
        first-non-empty dequeue round-robins across the heavy tiers instead of
        strictly preferring the lowest-index one; otherwise ``template`` and
        ``reclaim`` starve indefinitely behind a steady ``maintenance``/``bulk``
        trickle (#3). Governed workers keep strict tier priority verbatim
        (``template`` preempts ``reclaim`` by design). The floor serves only heavy
        tiers, so rotating the whole list is a pure round-robin over them."""
        base = self._ordered_queues or []
        if not self._floor or len(base) < 2:
            return base
        off = self._wrr_cursor % len(base)
        return list(base[off:]) + list(base[:off])

    def _fair_ordered_queues(self, defer_bg):
        """Per-poll dequeue order under multitenancy: for each flat fair lane in
        the static base set, its active per-category sub-queues in weighted-RR
        order (dropping categories at their in-flight cap while governing), then
        the flat lane itself as a catch-all for null-category / legacy /
        rolling-upgrade jobs. The background tier is skipped entirely while
        deferring; non-fair lanes (interactive/standard/legacy) stay verbatim."""
        active = self._discover_fair_queues()
        self._wrr_cursor += 1
        ordered = []
        for q in self._ordered_base_for_poll():
            parsed = parse_storage_queue(q.name)
            is_fair_base = bool(
                parsed and parsed[1] is None and parsed[2] in _FAIR_TIERS
            )
            if not is_fair_base:
                if defer_bg and is_deferrable_queue(q.name):
                    continue
                ordered.append(q)
                continue
            pool, _, tier = parsed
            if tier in DEFERRABLE_TIERS and defer_bg:
                continue  # whole deferrable tier (per-category lanes + base) hidden
            cats = active.get((pool, tier), [])
            if self._is_governing():
                cats = [c for c in cats if not self._category_at_cap(pool, c)]
            for c in self._weighted_rotation(
                cats, self.gov_category_weights, self._wrr_cursor
            ):
                ordered.append(self._make_fair_queue(f"storage.{pool}.{c}.{tier}"))
            # The flat catch-all's jobs have no category segment, so _admit reserves
            # them against the NULL_CATEGORY sentinel. Drop the catch-all lane too
            # while governing when that sentinel is at its cap — mirroring the
            # per-category at-cap drop above. Otherwise a queued null-category job is
            # popped, always denied by _reserve_fair, pushed back at front, and
            # re-popped: a no-sleep tight-spin. It reappears once the sentinel frees.
            if not (
                self._is_governing() and self._category_at_cap(pool, NULL_CATEGORY)
            ):
                ordered.append(q)  # flat catch-all AFTER the per-category lanes
        return ordered

    def _flat_ordered_queues(self, defer_bg):
        """Non-multitenancy dequeue order: the static base set (the pre-Phase-2
        behaviour), PLUS a drain lane for any per-category sub-queue that still
        exists on Redis. Those only appear transiently — a producer emitting
        ``storage.<pool>.<cat>.<tier>`` before this worker was recreated with the
        switch ON (producer-leads-worker), or leftover jobs after the switch was
        turned back OFF. Serving them here (ungoverned per-category, but still
        globally heavy-capped for background via the P1 ``_admit`` path) makes the
        switch safe to flip in EITHER recreate order and safe to turn back OFF —
        no category-lane job is ever stranded waiting for a discovering worker.
        In the steady OFF state no category lane exists, discovery returns empty,
        and this is exactly the pre-Phase-2 base set (zero behaviour change)."""
        self._wrr_cursor += 1
        base = [
            q
            for q in self._ordered_base_for_poll()
            if not (defer_bg and is_deferrable_queue(q.name))
        ]
        strays = []
        for (pool, tier), cats in self._discover_fair_queues().items():
            if defer_bg and tier in DEFERRABLE_TIERS:
                continue
            for c in sorted(cats):
                strays.append(self._make_fair_queue(f"storage.{pool}.{c}.{tier}"))
        return base + strays

    def _admit(self, job, queue, defer_bg):
        """Decide whether to run ``job`` from ``queue`` now. On admission record
        the reserved slots on the job (for execute_job to release) and return
        True. On denial — deferred, pressure risen while blocked, lost the atomic
        slot, or the per-category set is at cap — push the job back at the FRONT
        of its queue and return False so the caller steps aside and re-polls."""
        parsed = parse_storage_queue(queue.name)
        fair = bool(self.multitenancy and parsed and parsed[2] in _FAIR_TIERS)
        governing = self._is_governing()
        if fair and governing:
            pool, cat, tier = parsed
            category = cat if cat is not None else NULL_CATEGORY
            # ``capped`` (max-heavy concurrency) and ``deferrable`` (PSI hide) are
            # now distinct: reclaim defers under pressure but does NOT reserve a
            # global heavy slot (a trivial unlink/rename must not block a convert).
            capped = tier in HEAVY_TIERS
            deferrable = tier in DEFERRABLE_TIERS
            if (
                deferrable and (defer_bg or self._pressure_high())
            ) or not self._reserve_fair(job.id, pool, category, capped):
                queue.push_job_id(job.id, at_front=True)
                return False
            job._gov_reserved = ("fair", pool, category, capped)
            return True
        if not fair and governing and is_deferrable_queue(queue.name):
            # Flat (non-multitenancy) path: reclaim defers under pressure but is
            # not heavy-capped; template/maintenance defer AND reserve the slot.
            if defer_bg or self._pressure_high():
                queue.push_job_id(job.id, at_front=True)
                return False
            if is_heavy_queue(queue.name):
                if not self._reserve_heavy(job.id):
                    queue.push_job_id(job.id, at_front=True)
                    return False
                job._gov_reserved = ("heavy",)
            return True
        # Governor disabled / bg-floor / a non-heavy non-fair lane: run ungoverned
        # (no reservation, no release) — the ungoverned floor still makes progress.
        return True

    def _defer_background(self):
        """Whether heavy (background) queues must be hidden for this poll:
        under PSI pressure, or at the heavy cap after a leak-reconcile. Nothing is
        ever deferred by the kill-switch or the ungoverned bg-floor worker."""
        if not self._is_governing():
            return False
        if self._pressure_high():
            return True
        if self._heavy_at_cap():
            self._reconcile_heavy()
            return self._heavy_at_cap()
        return False

    # --- observability: publish live state for the apiv4 read layer ---------
    def _served_pools(self):
        """Best-effort set of pool ids this worker serves, from its static base
        queue set (``_fair_targets`` for an elastic worker, else parsed from the
        ordered queues for a reserved/standard one)."""
        pools = {pool for (pool, _tier) in self._fair_targets}
        if not pools:
            for q in self._ordered_queues or []:
                parsed = parse_storage_queue(q.name)
                if parsed:
                    pools.add(parsed[0])
        return sorted(pools)

    def _worker_kind(self):
        """This worker's class for the observability rows: ``floor`` (ungoverned
        bg-floor), ``elastic`` (governs fair tiers), else ``reserved``."""
        if self._floor:
            return "floor"
        return "elastic" if self._fair_targets else "reserved"

    def _publish_status(self, defer_bg):
        """Publish this worker's live governor state into ``governor:worker:<name>``
        (a self-expiring Redis HASH) for the apiv4 storage-governor read layer.

        Best-effort and RethinkDB-free: it reads only PSI files + the shared RQ
        Redis and NEVER raises — a Redis blip here must not wedge the hot dequeue
        loop. The hash self-expires (``_WORKER_STATUS_TTL``) so a dead worker's row
        disappears and the reader treats its absence as "worker down". ``psi_*``
        are the structural served set (NOT filtered by this poll's background
        deferral) so a transiently-deferring worker still reports coverage and the
        reader's StrandedLane check does not false-fire under momentary pressure;
        the transient state is carried separately in ``deferring``.
        """
        try:
            cpu_psi = rg.read_pressure(self.gov_cpu_psi_path)
        except Exception:
            cpu_psi = None
        try:
            io_psi = rg.read_pressure(self.gov_io_psi_path)
        except Exception:
            io_psi = None
        try:
            mem_psi = rg.read_pressure(self.gov_mem_psi_path)
        except Exception:
            mem_psi = None
        pools = self._served_pools()
        # Structural served lanes (the static base set) — stable coverage signal,
        # independent of this poll's transient background deferral.
        served = [q.name for q in (self._ordered_queues or [])]
        mapping = {
            "ts": repr(time.time()),
            "pool": pools[0] if pools else "",
            "pools": json.dumps(pools),
            "kind": self._worker_kind(),
            "governing": "1" if self._is_governing() else "0",
            "deferring": "1" if defer_bg else "0",
            "at_cap": "1" if self._heavy_at_cap() else "0",
            "floor": "1" if self._floor else "0",
            "multitenancy": "1" if self.multitenancy else "0",
            "served_lanes": json.dumps(served),
        }
        if cpu_psi is not None:
            mapping["psi_cpu"] = repr(cpu_psi)
        if io_psi is not None:
            mapping["psi_io"] = repr(io_psi)
        if mem_psi is not None:
            mapping["psi_mem"] = repr(mem_psi)
        if self._last_job_id is not None:
            mapping["last_job_id"] = str(self._last_job_id)
        if self._last_job_action is not None:
            mapping["last_job_action"] = str(self._last_job_action)
        try:
            key = worker_status_key(self.name)
            pipe = self.connection.pipeline()
            pipe.hset(key, mapping=mapping)
            pipe.expire(key, _WORKER_STATUS_TTL)
            pipe.execute()
        except Exception:
            pass

    # --- dequeue: gate heavy admission --------------------------------------
    def dequeue_job_and_maintain_ttl(self, timeout, max_idle_time=None):
        """Pressure-aware reimplementation of RQ's dequeue loop.

        Every poll we re-evaluate PSI / heavy-cap and choose the queue set: all
        queues, or (under pressure / at cap) only the non-background ones, so a
        cleared trough is picked up within ``gov_backoff`` and heavy work never
        runs under the pressure the governor exists to prevent. We block with a
        short ``gov_backoff`` timeout and loop — never returning ``None`` while
        blocking (that would quit the worker), only when a supplied
        ``max_idle_time`` budget is exhausted or on a ``--burst`` drain.
        """
        burst = timeout is None
        idle_deadline = (
            None if max_idle_time is None else time.monotonic() + max_idle_time
        )
        self.set_state(WorkerStatus.IDLE)
        self.procline("Listening on " + ",".join(self.queue_names()))
        while True:
            self.heartbeat()
            if self.should_run_maintenance_tasks:
                self.run_maintenance_tasks()

            # Pull the live governor knobs (DB->env->hardcoded) for this poll, so
            # an admin's edit is honoured within one cycle without a restart.
            self._refresh_live_config()
            poll = None if burst else self.gov_backoff
            defer_bg = self._defer_background()
            # Publish this worker's live state (best-effort, never wedges the
            # loop) for the apiv4 storage-governor observability read layer.
            self._publish_status(defer_bg)
            if self.multitenancy:
                # Discover per-category lanes and order them (weighted-RR) ahead
                # of the flat catch-all for this poll.
                queues = self._fair_ordered_queues(defer_bg)
            else:
                # Switch OFF: the flat base set, plus a drain lane for any stray
                # per-category sub-queue (transient during a switch flip) so it is
                # never stranded. Empty discovery == the pre-Phase-2 base set.
                queues = self._flat_ordered_queues(defer_bg)

            if not queues:
                # Nothing but background queues while deferring: wait a poll and
                # re-evaluate (never busy-spin, never quit).
                if burst or self._idle_expired(idle_deadline):
                    return None
                time.sleep(poll)
                continue

            # RQ's reliable-queue (intermediate) path fires when dequeue_any gets
            # EXACTLY ONE queue (rq/queue.py: ``len(queue_keys)==1`` -> BLMOVE into
            # ``<queue>:intermediate``), but its REMOVAL keys off the STATIC
            # ``len(self.queues)`` (rq/worker.py: ``remove_from_intermediate_queue
            # = len(self.queues)==1``). Our per-poll filtered set can be length 1
            # while the static set is larger, so the two disagree: the job is moved
            # into the intermediate list and NEVER removed, and RQ's later
            # maintenance sweep flips the already-SUCCEEDED job to ``failed``. Force
            # the multi-queue (non-reliable) branch by duplicating the sole queue —
            # exactly how a stock multi-queue worker already dequeues, and harmless
            # (Redis BLPOP over ``[k, k]`` just pops from ``k``). Guarded on the
            # static set being >1 so a genuinely single-queue worker keeps reliable
            # mode.
            if len(queues) == 1 and len(self._ordered_queues or []) > 1:
                queues = queues + queues

            try:
                result = self.queue_class.dequeue_any(
                    queues,
                    poll,
                    connection=self.connection,
                    job_class=self.job_class,
                    serializer=self.serializer,
                    death_penalty_class=self.death_penalty_class,
                )
            except DequeueTimeout:
                if self._idle_expired(idle_deadline):
                    return None
                continue  # re-check pressure, keep polling — do NOT return None
            if result is None:
                return None  # burst / non-blocking drain exhausted
            job, queue = result
            # Admit (P1 flat heavy-cap, or Phase-2 per-category fair) — on denial
            # the job was pushed back at the FRONT; step aside and re-poll. The
            # next poll's cap/pressure check keeps heavy work out, so this can't
            # tight-spin.
            if not self._admit(job, queue, defer_bg):
                if self._idle_expired(idle_deadline):
                    return None
                continue
            self.reorder_queues(reference_queue=queue)
            job.redis_server_version = self.get_redis_server_version()
            return job, queue

    @staticmethod
    def _idle_expired(idle_deadline):
        return idle_deadline is not None and time.monotonic() >= idle_deadline

    # --- release the reserved slot(s) after execution -----------------------
    def execute_job(self, job, queue):
        # Release exactly what _admit reserved for THIS job (set as an attribute
        # on the same in-parent job object). Counter-neutral for ungoverned /
        # kill-switch / bg-floor jobs, which set no flag and reserved nothing.
        reserved = getattr(job, "_gov_reserved", None)
        # Record the job this worker is BEGINNING to execute so the next status
        # publish (and a status hash that outlives a SIGKILL) attributes a
        # worker-killing poison job to its exact id/action (catalog #4b). The
        # action is the trailing segment of the ``task.<action>`` func name
        # (mirrors models.task.Task.task).
        self._last_job_id = job.id
        try:
            self._last_job_action = job.func_name.rsplit(".", 1)[-1]
        except Exception:
            self._last_job_action = None
        try:
            return super().execute_job(job, queue)
        finally:
            if reserved:
                if reserved[0] == "fair":
                    _, pool, category, is_heavy = reserved
                    self._release_fair(job.id, pool, category, is_heavy)
                elif reserved[0] == "heavy":
                    self._release_heavy(job.id)
