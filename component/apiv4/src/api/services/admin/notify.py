#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

from typing import Any, Dict, List, Optional

from api.schemas.admin.notify import DesktopQueueItem
from isardvdi_common.helpers.api_notify import (
    notify_custom,
    notify_desktop,
    notify_user,
)
from isardvdi_common.lib.domains.domains import DomainsProcessed


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
        domain_map = DomainsProcessed.get_user_id_by_desktop_id(
            [item.desktop_id for item in items]
        )

        users: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for item in items:
            user_id = domain_map.get(item.desktop_id)
            if user_id:
                users.setdefault(user_id, {})[item.desktop_id] = item.model_dump()

        for user_id, user_desktops in users.items():
            notify_custom("desktops_queue", user_desktops, "/userspace", user_id)
