#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


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
    """Single desktop queue entry"""

    desktop_id: str


class SocketioEmitRequest(BaseModel):
    """Request to emit a socketio event"""

    event: Optional[str] = None
    data: Optional[Any] = None
    namespace: Optional[str] = None
    room: Optional[str] = None
