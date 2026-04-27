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

import traceback
from datetime import datetime

import pytz
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.error_factory import Error
from isardvdi_common.helpers.helpers import Helpers
from isardvdi_common.helpers.log import logger
from isardvdi_common.lib.notifications.notifications_data import (
    NotificationsDataProcessed,
)
from isardvdi_common.lib.notifications.notifications_templates import (
    NotificationTemplatesProcessed,
)
from isardvdi_common.lib.users.users.user import UsersProcessed
from isardvdi_common.models.targets import Targets


class NotificationsCompute(RethinkSharedConnection):
    @classmethod
    def start_desktop_bastion(cls, payload, notification, lang):
        """
        Calculate the bastion notifications that must be shown to the user when a desktop is started.
        """
        start_desktop_notifications = []
        bastion_notification = cls.get_bastion_notification(payload, notification, lang)
        if bastion_notification:
            start_desktop_notifications.append(bastion_notification)

        return start_desktop_notifications

    @classmethod
    def get_bastion_notification(cls, payload, notification, lang):
        """
        Check if the user can use bastion and if the last started desktop has bastion enabled.
        If so, return a disclaimer notification to the user.

        :param payload: The payload of the request.
        :type payload: dict
        :return: A notification to the user.
        :rtype: dict
        """
        # If the installation has bastion activated, we need to check if the lastly started desktop has bastion enabled
        bastion_allowed = Helpers.can_use_bastion(payload)
        if bastion_allowed:
            # Get the last started desktop by the user
            last_desktop_log = UsersProcessed.get_user_last_started_desktop_log(
                payload["user_id"]
            )
            if last_desktop_log:
                try:
                    bastion = Targets.get_domain_target(last_desktop_log["desktop_id"])
                except Error as e:
                    # No bastion target configured → no notification to
                    # show. Any other typed error (forbidden, conflict,
                    # ...) must propagate so the caller can surface it.
                    if e.status_code == 404:
                        return {}
                    raise
                try:
                    if (
                        bastion.get("http") and bastion["http"].get("enabled") is True
                    ) or (bastion.get("ssh") and bastion["ssh"].get("enabled") is True):
                        # Get the notification template in the user language
                        notification_template_user = NotificationTemplatesProcessed.get_notification_template_by_kind(
                            "bastion_enabled_disclaimer"
                        )
                        notification_template_user_lang = notification_template_user[
                            "lang"
                        ].get(
                            lang,
                            notification_template_user["lang"][
                                notification_template_user["default"]
                            ],
                        )
                        notification_data = (
                            NotificationsDataProcessed.get_user_notifications_data(
                                payload["user_id"], "notified", notification["id"]
                            )
                        )
                        # If the user has not been notified yet, we need to create the notification data
                        if not notification_data:
                            notification_data = {
                                "accepted_at": None,
                                "created_at": datetime.now().astimezone(pytz.UTC),
                                "item_id": last_desktop_log["desktop_id"],
                                "item_type": "desktop",
                                "notification_id": notification["id"],
                                "notified_at": datetime.now().astimezone(pytz.UTC),
                                "status": "notified",
                                "user_id": payload["user_id"],
                                "vars": {
                                    "desktop_name": last_desktop_log["desktop_name"],
                                },
                                "ignore_after": notification["ignore_after"],
                            }
                            NotificationsDataProcessed.add_notification_data(
                                notification_data
                            )
                        # Otherwise, we need to update the notification data
                        else:
                            notification_data = notification_data[0]
                            NotificationsDataProcessed.update_notification_data(
                                {
                                    "id": notification_data["id"],
                                    "notified_at": datetime.now().astimezone(pytz.UTC),
                                }
                            )
                        return {
                            "id": "0000-000",
                            "title": notification_template_user_lang["title"],
                            "body": notification_template_user_lang["body"].format(
                                **notification_data["vars"]
                            ),
                            "footer": notification_template_user_lang["footer"],
                        }
                except Exception:
                    # Downstream failures (template lookup, notification-data
                    # DB ops, template formatting) degrade to "no
                    # notification" but are logged so operators see them.
                    logger.error(
                        "get_bastion_notification: failed to assemble "
                        "notification for user %s: %s",
                        payload.get("user_id"),
                        traceback.format_exc(),
                    )
                    return {}
        return {}
