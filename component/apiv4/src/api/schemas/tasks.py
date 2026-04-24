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


class TaskListResponse(BaseModel):
    """List of tasks"""

    tasks: List[Dict[str, Any]]
