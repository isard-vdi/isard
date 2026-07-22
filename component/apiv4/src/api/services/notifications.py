#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Miriam Melina Gamboa Valdez
#
#   This program is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or
#   (at your option) any later version.
#
#   This program is distributed in the hope that it will be useful,
#   but WITHOUT ANY WARRANTY; without even the implied warranty of
#   MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#   GNU Affero General Public License for more details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from isardvdi_common.lib.notifications.notifications import NotificationsProcessed
from isardvdi_common.lib.notifications.notifications_data import (
    NotificationsDataProcessed,
)


class NotificationService:

    @staticmethod
    def get_user_trigger_notifications_displays(
        token_payload: dict, trigger: str
    ) -> list[str]:
        return NotificationsProcessed.get_user_trigger_notifications_displays(
            token_payload, trigger
        )

    @staticmethod
    def get_user_trigger_notifications(
        token_payload: dict, trigger: str, display: str
    ) -> dict:
        return NotificationsProcessed.get_user_trigger_notifications(
            token_payload, trigger, display
        )

    @staticmethod
    def get_user_trigger_notifications_flat(
        token_payload: dict, trigger: str, display: str
    ) -> list[dict]:
        """Flatten the nested trigger/display response into an ordered list.

        Resolves the user's language template against each item so the
        client receives `{id, title, body, footer, force_accept}` entries
        ready to render.
        """
        nested = NotificationsProcessed.get_user_trigger_notifications(
            token_payload, trigger, display
        )
        flat = []
        for order in sorted(nested.keys()):
            for group in nested[order].values():
                template = group.get("template") or {}
                force_accept = bool(group.get("force_accept", False))
                for item in group.get("notifications", []):
                    item_vars = item.get("vars") or {}
                    flat.append(
                        {
                            "id": item.get("id", ""),
                            "title": item.get("title")
                            or item_vars.get("title")
                            or template.get("title")
                            or "",
                            "body": item.get("body")
                            or item_vars.get("body")
                            or item.get("text")
                            or template.get("body")
                            or "",
                            "footer": item.get("footer") or template.get("footer"),
                            "force_accept": force_accept,
                        }
                    )
        return flat

    @staticmethod
    def delete_expired_notifications_data() -> None:
        return NotificationsDataProcessed.delete_expired_notifications_data()
