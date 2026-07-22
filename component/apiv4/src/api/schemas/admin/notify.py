#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, RootModel


class NotifyUserDesktopRequest(BaseModel):
    """Request to notify a user about a desktop"""

    user_id: str
    type: str
    msg_code: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


class NotifyDesktopRequest(BaseModel):
    """Request to notify a desktop"""

    desktop_id: str
    type: str
    msg_code: Optional[str] = None
    params: Optional[Dict[str, Any]] = None


class DesktopQueueItem(BaseModel):
    """Single desktop queue entry.

    Matches the exact shape produced by
    ``hyp_worker_thread.get_positioned_items``
    (``engine/.../hyp_worker_thread.py``): the engine always emits
    ``desktop_id``, ``event``, ``priority`` and ``position`` — these
    four fields are the complete contract. Unknown keys are rejected
    (``extra="forbid"``) so a new field on the engine side surfaces
    as a 422 here and forces us to update this schema in lockstep
    rather than silently drifting.
    """

    model_config = ConfigDict(extra="forbid")

    desktop_id: str
    event: Optional[str] = None
    priority: Optional[int] = None
    position: Optional[int] = None


class AdminNotifyDesktopsQueueRequest(RootModel[List[DesktopQueueItem]]):
    """Top-level JSON array body for ``PUT /admin/item/notify/desktops/queue/{hyp_id}``."""

    pass


class SocketioEmitRequest(BaseModel):
    """Single socketio event."""

    event: Optional[str] = None
    data: Optional[Any] = None
    namespace: Optional[str] = None
    room: Optional[str] = None


class AdminSocketioEmitRequest(RootModel[List[SocketioEmitRequest]]):
    """Top-level JSON array body for ``POST /admin/items/socketio``."""

    pass
