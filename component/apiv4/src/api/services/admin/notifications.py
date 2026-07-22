#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Naomi Hidalgo Piñar
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

from datetime import datetime
from typing import Any, Dict, List, Optional

import pytz
from api.services.error import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.lib.notifications.notifications import NotificationsProcessed
from isardvdi_common.lib.notifications.notifications_action import (
    NotificationsActionProcessed,
)
from isardvdi_common.lib.notifications.notifications_data import (
    NotificationsDataProcessed,
)
from isardvdi_common.lib.notifications.notifications_templates import (
    NotificationTemplatesProcessed,
)
from isardvdi_common.lib.users.users.user import UsersProcessed
from isardvdi_common.models.config import Config

FORBIDDEN_TAGS = ["<script", "<iframe", "javascript:"]


class AdminNotificationService:

    # --- Templates ---

    @staticmethod
    def create_template(data: dict) -> str:
        body_lower = data.get("body", "").lower()
        footer_lower = data.get("footer", "").lower()
        for tag in FORBIDDEN_TAGS:
            if tag in body_lower or tag in footer_lower:
                raise Error(
                    "bad_request",
                    "Invalid expression in body or footer",
                    description_code="bad_request",
                )

        language = data.pop("language")
        data["lang"] = {
            language: {
                "title": data.pop("title"),
                "body": data.pop("body"),
                "footer": data.pop("footer"),
            }
        }

        return NotificationTemplatesProcessed.add_notification_template(data)

    @staticmethod
    def get_templates(kind: Optional[str] = None) -> list:
        return NotificationTemplatesProcessed.get_notification_templates(kind)

    @staticmethod
    def get_template(template_id: str) -> dict:
        return NotificationTemplatesProcessed.get_notification_template(template_id)

    @staticmethod
    def update_template(template_id: str, data: dict) -> None:
        body_lower = data.get("body", "").lower()
        footer_lower = data.get("footer", "").lower()
        for tag in FORBIDDEN_TAGS:
            if tag in body_lower or tag in footer_lower:
                raise Error(
                    "bad_request",
                    "Invalid expression in body or footer",
                    description_code="bad_request",
                )

        language = data.pop("language")
        data["lang"] = {
            language: {
                "title": data.pop("title"),
                "body": data.pop("body"),
                "footer": data.pop("footer"),
            }
        }

        NotificationTemplatesProcessed.update_notification_template(template_id, data)

    @staticmethod
    def preview_template(event: str, user_id: Optional[str], data: dict) -> dict:
        return NotificationTemplatesProcessed.get_notification_event_template(
            event, user_id, data
        )

    @staticmethod
    def delete_template(template_id: str) -> None:
        NotificationTemplatesProcessed.delete_notification_template(template_id)

    # --- Notifications CRUD ---

    @staticmethod
    def get_all_notifications() -> list:
        return NotificationsProcessed.get_all_notifications()

    @staticmethod
    def create_notification(data: dict) -> str:
        if data.get("ignore_after"):
            data["ignore_after"] = datetime.strptime(
                data["ignore_after"], "%Y-%m-%dT%H:%M"
            ).astimezone(pytz.UTC)

        NotificationsProcessed.add_notification(data)
        return data.get("id", "")

    @staticmethod
    def get_notification_actions() -> list:
        return NotificationsActionProcessed.get_all_notification_actions()

    @staticmethod
    def get_notification(notification_id: str) -> dict:
        return NotificationsProcessed.get_notification(notification_id)

    @staticmethod
    def update_notification(notification_id: str, data: dict) -> None:
        if data.get("ignore_after"):
            data["ignore_after"] = datetime.strptime(
                data["ignore_after"], "%Y-%m-%dT%H:%M"
            ).astimezone(pytz.UTC)

        NotificationsProcessed.update_notification(notification_id, data)

    @staticmethod
    def delete_notification(notification_id: str, delete_logs: bool = True) -> None:
        NotificationsProcessed.delete_notification(notification_id, delete_logs)

    # --- Notification Data ---

    @staticmethod
    def get_notifications_data_by_status(status: str, user_id: str) -> list:
        return NotificationsDataProcessed.get_notifications_data_by_status(
            status, user_id
        )

    @staticmethod
    def get_notification_statuses() -> list:
        return NotificationsDataProcessed.get_notification_statuses()

    @staticmethod
    def get_notifications_grouped_by_status(status: str) -> list:
        return NotificationsDataProcessed.get_notifications_grouped_by_status(status)

    @staticmethod
    def delete_user_notification_data(user_id: str) -> None:
        NotificationsDataProcessed.delete_users_notifications_data([user_id])

    @staticmethod
    def delete_notification_data(notification_data_id: str) -> None:
        NotificationsDataProcessed.delete_notifications_data(notification_data_id)

    @staticmethod
    def delete_all_notification_data() -> None:
        NotificationsDataProcessed.delete_all_notification_data()

    # --- User displays (admin) ---

    @staticmethod
    def get_user_displays(user_id: str, trigger: str) -> list:
        user_payload = Helpers.gen_payload_from_user(user_id)
        return NotificationsProcessed.get_user_trigger_notifications_displays(
            user_payload, trigger
        )

    # --- Status bar (user-facing) ---

    @staticmethod
    def get_status_bar_notification(payload: dict) -> dict | None:
        """Return the status-bar notification for the calling user.

        Mirrors v3 ``AdminNotificationsView.api_v3_get_status_bar_notifications``
        (``@has_token``). Looks up the current user's language and the
        provider-level status-bar notification template. Returns
        ``None`` when the template is disabled or neither
        migration direction is enabled for the user's provider.
        """
        provider = payload.get("provider")
        notification = (
            NotificationTemplatesProcessed.get_status_bar_notification_by_provider(
                provider
            )
        )
        provider_config = Config.get_provider_config(provider)

        if notification["enabled"] and (
            provider_config["migration"]["export"]
            or provider_config["migration"]["import"]
        ):
            notification_tmpl = (
                NotificationTemplatesProcessed.get_notification_template(
                    notification.get("template")
                )
            )
            lang = UsersProcessed.get_user_language(payload.get("user_id"))
            if notification_tmpl["lang"].get(lang):
                notification_text = notification_tmpl["lang"][lang]
            else:
                notification_text = notification_tmpl["lang"][
                    notification_tmpl["default"]
                ]
            return {
                "text": notification_text["body"],
                "level": notification["level"],
                "migration_config": {
                    "import": provider_config["migration"]["import"],
                    "export": provider_config["migration"]["export"],
                },
            }
        return None
