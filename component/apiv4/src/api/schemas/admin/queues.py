#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Annotated, Dict, List, Optional, Union

from pydantic import BaseModel, Field


class QueueJobsResponse(BaseModel):
    """Queue jobs summary"""

    id: str
    queued: int = 0
    started: int = 0
    finished: int = 0
    failed: int = 0
    deferred: int = 0
    scheduled: int = 0
    canceled: int = 0


class QueueJobsListResponse(BaseModel):
    """List of queue job summaries"""

    queues: List[QueueJobsResponse]


class QueueConsumerResponse(BaseModel):
    """Queue consumer/worker info.

    Back-compatible superset of the legacy pubsub-derived shape (``id``/
    ``queue``/``priority``/``subscribers``/``status``) PLUS the reworked
    heartbeat-truth fields sourced from the bounded ``rq:workers`` SET and each
    ``rq:worker:<name>`` hash (and, once published in a later step, the
    ``governor:worker:<name>`` hash — until then PSI/served-lanes degrade to
    ``null``/``served_known=false``). Every new field is Optional so an old
    consumer of this endpoint keeps working.
    """

    id: str
    queue: str
    queue_id: Optional[str] = None
    priority_id: Optional[str] = None
    priority: Optional[int] = None
    subscribers: Optional[List[str]] = None
    status: Optional[str] = None
    # --- reworked heartbeat / served / governor fields ---
    name: Optional[str] = None
    pool: Optional[str] = None
    kind: Optional[str] = None
    state: Optional[str] = None
    up: Optional[bool] = None
    hash_present: Optional[bool] = None
    last_heartbeat: Optional[float] = None
    heartbeat_age_seconds: Optional[float] = None
    current_lane: Optional[str] = None
    served_lanes: Optional[List[str]] = None
    served_known: Optional[bool] = None
    psi_cpu: Optional[float] = None
    psi_io: Optional[float] = None
    psi_mem: Optional[float] = None
    deferring: Optional[bool] = None
    at_cap: Optional[bool] = None
    floor: Optional[bool] = None
    multitenancy: Optional[bool] = None
    last_job_id: Optional[str] = None
    last_job_action: Optional[str] = None


class DeleteOldTasksRequest(BaseModel):
    """Request to delete old tasks"""

    older_than: int


class DeleteOldTasksResult(BaseModel):
    """Result of deleting old tasks"""

    ok: List[str]
    errors: List[str]


class QueueRegistriesRequest(BaseModel):
    """Request to set queue registries"""

    queue_registries: Optional[List[str]] = []


class AutoDeleteEnabledRequest(BaseModel):
    """Request to set auto delete enabled"""

    enabled: bool


class AutoDeleteConfigResponse(BaseModel):
    """Auto delete configuration"""

    older_than: Optional[int] = None
    queue_registries: Optional[List[str]] = []
    enabled: bool = False


class AutoDeleteMaxTimeResponse(BaseModel):
    """Response shape for ``PUT /admin/item/queues/old_tasks/config/max_time/{max_time}``."""

    older_than: int


class AutoDeleteQueueRegistriesResponse(BaseModel):
    """Response shape for ``PUT /admin/item/queues/old_tasks/config/queue_registries``."""

    queue_registries: List[str]


class AutoDeleteEnabledResponse(BaseModel):
    """Response shape for ``PUT /admin/item/queues/old_tasks/config/enabled``."""

    enabled: bool


class StorageSchedulerConfigResponse(BaseModel):
    """Live storage-governor config (``config[1].storage_scheduler``)."""

    enabled: bool = True
    psi_limit: float = 40.0
    max_heavy: int = 2
    backoff: int = 3
    # Per-category fairness knobs (elastic pool bulk/background). Weights bias the
    # weighted round-robin share; the per-category and default in-flight caps bound
    # each category's concurrency. An unset default cap (``None``) means uncapped —
    # the weighted-RR ordering alone provides fairness (work-conserving).
    category_weights: Dict[str, int] = {}
    category_max_inflight: Dict[str, int] = {}
    category_default_max_inflight: Optional[int] = None


class StorageSchedulerConfigRequest(BaseModel):
    """Partial update of the live storage-governor config; only the provided
    keys are written (siblings preserved). Bounds are enforced at the edge so an
    out-of-range value is rejected rather than bricking the elastic workers."""

    enabled: Optional[bool] = None
    psi_limit: Optional[float] = Field(default=None, ge=0, le=100)
    # Upper bounds (review #11): backoff at/above the worker-status TTL (90s)
    # self-locks the fleet (every worker's hash expires between polls -> reported
    # DOWN, config unreadable); an unbounded weight/cap materialises a huge
    # per-poll list -> OOM. max_heavy is a resource-footprint cap.
    max_heavy: Optional[int] = Field(default=None, ge=1, le=64)
    backoff: Optional[int] = Field(default=None, ge=1, le=60)
    # Per-category fairness knobs. Each weight / cap is a positive integer; a
    # supplied map REPLACES the stored one (send the full map to edit it). The
    # default cap accepts a positive int; leave it out to keep the current value
    # (unset == uncapped, weighted-RR-only).
    category_weights: Optional[Dict[str, Annotated[int, Field(ge=1, le=1000)]]] = None
    category_max_inflight: Optional[Dict[str, Annotated[int, Field(ge=1, le=1000)]]] = (
        None
    )
    category_default_max_inflight: Optional[int] = Field(default=None, ge=1, le=1000)


# =============================================================================
# STORAGE-GOVERNOR OBSERVABILITY GAUGES (read layer — P2.4 §2.3/§2.4)
# =============================================================================


class RedisHealth(BaseModel):
    """Broker (RQ Redis) health sampled once per governor read (catalog #15)."""

    up: bool = False
    ping_ms: Optional[float] = None
    used_memory: Optional[int] = None
    maxmemory: Optional[int] = None
    used_ratio: Optional[float] = None
    evicted_keys: Optional[int] = None


class HeavyGauge(BaseModel):
    """Global heavy-admission gauge: ``SCARD(governor:heavy_running)`` vs the
    effective ``max_heavy`` cap, plus the read-only leak delta (catalog #5/#12)."""

    running: int = 0
    cap: int = 0
    at_cap: bool = False
    leaked: int = 0


class WorkerHealthRow(BaseModel):
    """Per-worker heartbeat + governor-published row.

    ``up``/``hash_present``/``heartbeat_age_seconds`` come from the bounded
    ``rq:workers`` SET and the ``rq:worker:<name>`` hash. PSI / ``deferring`` /
    ``served_lanes`` / ``multitenancy`` / ``last_job_*`` come from the
    ``governor:worker:<name>`` hash, which is NOT published yet (a later step) —
    until then those degrade to ``null`` and ``served_known=false``. Deliberately
    has NO ``current_job_runtime_seconds`` (catalog #2b is backed instead by the
    problem-tasks endpoint + the per-pool ``started_over_timeout`` gauge)."""

    name: str
    pool: Optional[str] = None
    kind: Optional[str] = None
    state: Optional[str] = None
    up: bool = False
    hash_present: bool = False
    last_heartbeat: Optional[float] = None
    heartbeat_age_seconds: Optional[float] = None
    current_lane: Optional[str] = None
    served_lanes: List[str] = []
    served_known: bool = False
    psi_cpu: Optional[float] = None
    psi_io: Optional[float] = None
    psi_mem: Optional[float] = None
    deferring: Optional[bool] = None
    at_cap: Optional[bool] = None
    floor: Optional[bool] = None
    multitenancy: Optional[bool] = None
    last_job_id: Optional[str] = None
    last_job_action: Optional[str] = None


class CategoryGauge(BaseModel):
    """Per-category fair-tier gauge (bulk/background only — reserved tiers have
    NO per-tenant inflight signal). ``category_id`` is ``_nocat`` for the
    null-owner sentinel lane; ``cap`` is ``None`` when uncapped (weighted-RR
    only)."""

    category_id: str
    category_name: Optional[str] = None
    inflight: int = 0
    cap: Optional[int] = None
    at_cap: bool = False
    weight: int = 1
    leaked: int = 0
    starved: bool = False
    backlog: Dict[str, int] = {}
    oldest_queued_age_seconds: Dict[str, float] = {}
    failed: Dict[str, int] = {}


class PoolGauge(BaseModel):
    """Per-pool rollup: per-tier backlog / oldest-queued-age / started-over-
    timeout / failed, plus the fair-tier per-category breakdown."""

    pool: str
    backlog: Dict[str, int] = {}
    oldest_queued_age_seconds: Dict[str, float] = {}
    started_over_timeout: Dict[str, int] = {}
    failed: Dict[str, int] = {}
    categories: List[CategoryGauge] = []


class GovernorWarning(BaseModel):
    """A single governor warning. ``kind`` selects which of the (all-Optional)
    fields are populated: ``stranded_lane`` (pool/tier/lane/backlog/
    coverage_known), ``leaked_inflight`` (scope/counted/live), ``category_starved``
    (pool/category_id), ``scheduled_overdue`` (pool/count/max_lateness_seconds)."""

    kind: str
    pool: Optional[str] = None
    tier: Optional[str] = None
    lane: Optional[str] = None
    category_id: Optional[str] = None
    backlog: Optional[int] = None
    coverage_known: Optional[bool] = None
    scope: Optional[str] = None
    counted: Optional[int] = None
    live: Optional[int] = None
    count: Optional[int] = None
    max_lateness_seconds: Optional[float] = None


class GovernorGaugesResponse(BaseModel):
    """Composite storage-governor gauge document — the ``GET
    /admin/items/queues/governor`` payload AND the stats-go scrape source
    (P2.4 §2.4). Degrades to honesty fields (``redis.up=false``, high
    ``data_age_seconds``, ``multitenancy_active="unknown"``, empty pools/workers)
    on transient Redis/rdb failure instead of raising."""

    generated_at: float
    data_age_seconds: float = 0.0
    # worker-reported structural flag (NOT lane-shape inferred); "unknown" when
    # no live worker reports it.
    multitenancy_active: Union[bool, str] = "unknown"
    config_enabled: bool = True
    config_mirrored: bool = True
    psi_limit: float = 40.0
    redis: RedisHealth = RedisHealth()
    heavy: HeavyGauge = HeavyGauge()
    pools: List[PoolGauge] = []
    workers: List[WorkerHealthRow] = []
    warnings: List[GovernorWarning] = []
    truncated_lanes: int = 0
    truncated_inflight: int = 0
    # effective/clamped config the elastic workers enforce (embedded for the
    # governor card; the config panel still binds to the storage_scheduler GET/PUT).
    config: Optional[StorageSchedulerConfigResponse] = None


class BacklogRollupRow(BaseModel):
    """One ``(pool, category, tier)`` backlog rollup row — the ``GET
    /admin/items/queues/backlog`` payload is a bare list of these (P2.4 §2.4)."""

    pool: str
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    tier: str
    queued: int = 0
    started: int = 0
    started_over_timeout: int = 0
    failed: int = 0
    deferred: int = 0
    oldest_queued_age_seconds: Optional[float] = None
    has_consumer: bool = False
    coverage_known: bool = False
    stranded: bool = False


class ProblemTask(BaseModel):
    """One row of the bounded, filterable problem-task listing (``GET
    /admin/items/queues/tasks/problems`` — P2.4 §2.4).

    ``kind`` is one of ``failed`` / ``stuck_running`` / ``deferred_orphan``.
    Timestamps are the tz-aware rq-job datetimes flattened to epoch-float wire
    form (``None`` when the job has not reached that lifecycle point).
    ``age_seconds`` is measured from the most-relevant timestamp for the kind
    (failed / deferred -> ``enqueued_at``; stuck_running -> ``started_at``).
    ``exc_string`` is the traceback of the latest FAILED result (never a metric
    label). ``retryable`` is True only for the failed kind; ``cancelable`` is
    True for all (admin cancel has no status gate)."""

    id: str
    kind: str
    action: Optional[str] = None
    queue: Optional[str] = None
    pool: Optional[str] = None
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    tier: Optional[str] = None
    job_status: Optional[str] = None
    pending: Optional[bool] = None
    retries_left: Optional[int] = None
    enqueued_at: Optional[float] = None
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    age_seconds: Optional[float] = None
    exc_string: Optional[str] = None
    retryable: bool = False
    cancelable: bool = True


class ProblemTasksResponse(BaseModel):
    """The ``GET /admin/items/queues/tasks/problems`` payload (P2.4 §2.4).

    Degrades to ``count=0`` / empty ``tasks`` on transient Redis failure rather
    than raising — a polled 500 would eject the operator mid-incident.
    ``truncated`` is set when any lane hit its per-lane scan cap or the merged
    pre-slice count exceeded the requested window."""

    generated_at: float
    truncated: bool = False
    count: int = 0
    tasks: List[ProblemTask] = []
