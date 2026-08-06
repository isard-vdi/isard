#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class TaskResponse(BaseModel):
    """Single task response"""

    id: str
    user_id: Optional[str] = None
    task: Optional[str] = None
    status: Optional[str] = None
    progress: Optional[float] = None
    queue: Optional[str] = None
    position: Optional[int] = None
    result: Optional[Any] = None
    exc_info: Optional[str] = None
    pending: Optional[bool] = None
    depending_status: Optional[str] = None
    job_status: Optional[str] = None
    storage_id: Optional[str] = None
    args: Optional[List[Any]] = None
    kwargs: Optional[Dict[str, Any]] = None
    dependencies: Optional[List[Dict[str, Any]]] = None
    dependents: Optional[List[Dict[str, Any]]] = None
    # Observability enrichment (get_task single-task path only). ``category_id``
    # already flows off the Task model once the schema admits it; the rest are
    # best-effort populated from the rq job in ``TaskService.get_task``.
    category_id: Optional[str] = None
    category_name: Optional[str] = None
    tier: Optional[str] = None
    enqueued_at: Optional[float] = None
    started_at: Optional[float] = None
    ended_at: Optional[float] = None
    age_seconds: Optional[float] = None
    retries_left: Optional[int] = None
    exc_string: Optional[str] = None
    # Live queue estimate (single-task path only). ``effective_position`` counts
    # the backlog of higher-priority tiers ahead of this task, not just its own
    # lane; ``eta_seconds`` is null until a service-time sample exists.
    effective_position: Optional[int] = None
    eta_seconds: Optional[float] = None
    has_consumer: Optional[bool] = None
    stranded: Optional[bool] = None


class OwnerTaskItem(BaseModel):
    """One row of "the tasks this storage or media has had".

    Deliberately not ``TaskResponse``. That model is shaped by the single-task
    detail path: its observability fields are filled by an enrichment step a
    listing must never run (a Redis fetch per row), and its ``storage_id``
    comes off a Task property that ``to_dict`` excludes — so reusing it here
    would put a dozen permanently null keys on the wire and imply a chain view
    this listing does not compute. Every field below is read from the job hash
    the batch already fetched.

    ``job_status`` is this job's own status, not its chain's: the chain status
    would mean walking dependencies, one round trip per member.
    """

    id: str
    task: Optional[str] = None
    queue: Optional[str] = None
    job_status: Optional[str] = None
    user_id: Optional[str] = None
    category_id: Optional[str] = None
    storage_id: Optional[str] = None
    media_id: Optional[str] = None
    enqueued_at: Optional[float] = None
    started_at: Optional[float] = None
    ended_at: Optional[float] = None


class TaskListResponse(BaseModel):
    """List of tasks"""

    tasks: List[Dict[str, Any]]


class QueueTierHealth(BaseModel):
    """Compact per-tier queued rollup for the user health summary."""

    tier: Optional[str] = None
    queued: int = 0
    stranded: bool = False


class QueuesHealthResponse(BaseModel):
    """User-facing storage-queue health summary (no per-worker detail)."""

    degraded: bool = False
    stranded: bool = False
    tiers: List[QueueTierHealth] = []
