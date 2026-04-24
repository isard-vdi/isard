#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from api.services.error import Error
from isardvdi_common.helpers.api_notify import notify_broadcast, notify_custom


class AdminSocketioService:
    """Service for admin socketio emit operations."""

    @staticmethod
    def emit_events(events: list):
        """Emit socketio events."""
        for event in events:
            notify_custom(
                event.get("event", "message"),
                event.get("data", {}),
                event.get("namespace", "/"),
                event.get("room", ""),
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
