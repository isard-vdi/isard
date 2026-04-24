#
#   Copyright © 2025 IsardVDI
#
#   SPDX-License-Identifier: AGPL-3.0-or-later

import traceback

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
        user_id: str, type: str, msg_code: str = None, params: dict = None
    ):
        """Send a notification to a user about a desktop."""
        notify_user(user_id, type, msg_code, params or {})

    @staticmethod
    def notify_desktop(
        desktop_id: str, type: str, msg_code: str = None, params: dict = None
    ):
        """Send a notification to a desktop."""
        notify_desktop(desktop_id, type, msg_code, params or {})

    @staticmethod
    def notify_desktop_queue(data: list, hyp_id: str):
        """Parse desktop queues and notify users."""
        from isardvdi_common.connections.rethink_connection_factory import (
            RethinkSharedConnection,
        )
        from rethinkdb import r

        desktop_ids = [entry["desktop_id"] for entry in data]

        with RethinkSharedConnection._rdb_context():
            domains = list(
                r.table("domains")
                .get_all(r.args(desktop_ids), index="id")
                .pluck("id", "user")
                .run(RethinkSharedConnection._rdb_connection)
            )

        domain_map = {domain["id"]: domain["user"] for domain in domains}

        users = {}
        for entry in data:
            desktop_id = entry["desktop_id"]
            user_id = domain_map.get(desktop_id)
            if user_id:
                users.setdefault(user_id, {})[desktop_id] = entry

        for user_id, user_desktops in users.items():
            notify_custom("desktops_queue", user_desktops, "/userspace", user_id)
