#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import traceback
from typing import Any, Dict, List, Optional

from api.schemas.admin.notify import DesktopQueueItem
from api.services.error import Error
from isardvdi_common.helpers.api_notify import (
    notify_custom,
    notify_desktop,
    notify_user,
)


class AdminNotifyService:
    """Service for admin notification sending operations."""

    @staticmethod
    def notify_user_desktop(
        user_id: str,
        type: str,
        msg_code: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send a notification to a user about a desktop."""
        notify_user(user_id, type, msg_code, params or {})

    @staticmethod
    def notify_desktop(
        desktop_id: str,
        type: str,
        msg_code: Optional[str] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Send a notification to a desktop."""
        notify_desktop(desktop_id, type, msg_code, params or {})

    @staticmethod
    def notify_desktop_queue(items: List[DesktopQueueItem], hyp_id: str) -> None:
        """Parse desktop queues and notify users. Accepts typed
        ``DesktopQueueItem`` models directly (not dicts) so the contract
        checked in :mod:`api.schemas.admin_notify` is preserved all the
        way down to the service boundary."""
        from isardvdi_common.connections.rethink_connection_factory import (
            RethinkSharedConnection,
        )
        from rethinkdb import r

        desktop_ids = [item.desktop_id for item in items]

        with RethinkSharedConnection._rdb_context():
            domains = list(
                r.table("domains")
                .get_all(r.args(desktop_ids), index="id")
                .pluck("id", "user")
                .run(RethinkSharedConnection._rdb_connection)
            )

        domain_map = {domain["id"]: domain["user"] for domain in domains}

        users: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for item in items:
            user_id = domain_map.get(item.desktop_id)
            if user_id:
                users.setdefault(user_id, {})[item.desktop_id] = item.model_dump()

        for user_id, user_desktops in users.items():
            notify_custom("desktops_queue", user_desktops, "/userspace", user_id)
