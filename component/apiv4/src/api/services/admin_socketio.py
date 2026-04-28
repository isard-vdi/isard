#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import List

from api.schemas.admin_notify import SocketioEmitRequest
from api.services.error import Error
from isardvdi_common.helpers.api_notify import notify_broadcast, notify_custom


class AdminSocketioService:
    """Service for admin socketio emit operations."""

    @staticmethod
    def emit_events(events: List[SocketioEmitRequest]):
        """Emit typed socketio events. Accepts ``SocketioEmitRequest``
        models directly so optional-field defaults live in the schema
        rather than being duplicated as ``.get(..., default)`` calls
        here."""
        for event in events:
            notify_custom(
                event.event or "message",
                event.data if event.data is not None else {},
                event.namespace or "/",
                event.room or "",
            )
        return True

    @staticmethod
    def broadcast(type_: str, message: str):
        """
        Broadcast an admin message to every connected client: fans out
        `msg` on ``/administrators`` and `msg_<type>` on ``/userspace``.
        """
        payload = {"type": type_, "msg": message}
        notify_broadcast("msg", payload, "/administrators")
        notify_broadcast(f"msg_{type_}", payload, "/userspace")
