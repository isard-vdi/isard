#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


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
    """Queue consumer/worker info"""

    id: str
    queue: str
    queue_id: Optional[str] = None
    priority_id: Optional[str] = None
    priority: Optional[int] = None
    subscribers: Optional[List[str]] = None
    status: Optional[str] = None


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
