#
#   IsardVDI - Open Source KVM Virtual Desktops based on KVM Linux and dockers
#   Copyright (C) 2025 Josep Maria Viñolas Auquer, Miriam Melina Gamboa Valdez
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

import logging as log
from datetime import datetime

import pytz
from cachetools import cached
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.alloweds import Alloweds
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
from isardvdi_common.lib.notifications.compute import NotificationsCompute
from isardvdi_common.lib.notifications.notifications_data import (
    NotificationsDataProcessed,
)
from isardvdi_common.lib.notifications.notifications_templates import (
    NotificationTemplatesProcessed,
)
from isardvdi_common.lib.users.users.user import UsersProcessed
from rethinkdb import r

notifications_cache = SynchronizedTTLCache(maxsize=10, ttl=30)


class NotificationsProcessed(RethinkSharedConnection):

    _rdb_table = "notifications"
    computed_functions_mapping = {
        "start_desktop_bastion": NotificationsCompute.start_desktop_bastion,
    }

    @classmethod
    def get_item_notifications_by_trigger(cls, trigger, enabled=True, display=None):
        """
        Returns the notifications for a specific trigger.

        :param trigger: The trigger.
        :type trigger: str
        :param enabled: Filter by enabled notifications.
        :type enabled: bool
        :param display: Filter by display.
        :type display: str or None
        :return: The notifications.
        :rtype: list
        """
        query = r.table(cls._rdb_table).get_all(
            [trigger, enabled], index="trigger_enabled"
        )
        if display:
            query = query.filter(
                lambda notification: notification["display"].contains(display)
            )
        with cls._rdb_context():
            return list(query.order_by(r.desc("order")).run(cls._rdb_connection))

    @classmethod
    def get_user_trigger_notifications_displays(cls, payload, trigger):
        """
        Checks if the user has notifications for the given trigger, returns the displays.

        :param payload: The payload of the request
        :type payload: dict
        :param trigger: The trigger to get the notifications for
        :type trigger: str
        :return: A list of displays if the user has notifications for the given trigger, empty list otherwise
        :rtype: list
        """
        all_notifications = cls.get_item_notifications_by_trigger(trigger)

        # Filter only the allowed notifications
        notifications = []
        for notification in all_notifications:
            if Alloweds.is_allowed(payload, notification, "notifications", True):
                notifications.append(notification)

        displays = []
        # Check if the user has notifications for the trigger
        for notification in notifications:
            # Check if the notification must be ignored
            if notification.get(
                "ignore_after", datetime(1970, 1, 1, tzinfo=pytz.UTC)
            ) != datetime(1970, 1, 1, tzinfo=pytz.UTC) and notification.get(
                "ignore_after", datetime(1970, 1, 1, tzinfo=pytz.UTC)
            ) < datetime.now().astimezone(
                pytz.UTC
            ):
                continue
            if notification["action_id"] == "custom":
                notifications_data = (
                    NotificationsDataProcessed.get_user_notifications_data(
                        payload["user_id"], "notified", notification["id"]
                    )
                )
                if not notifications_data:
                    displays += notification["display"]
            else:
                notifications_data = (
                    NotificationsDataProcessed.get_user_notifications_data(
                        payload["user_id"], "pending", notification["id"], True
                    )
                )
                if notifications_data:
                    displays += notification["display"]

        return list(set(displays))

    @classmethod
    def get_user_trigger_notifications(cls, payload, trigger, display):
        """
        Gets a list of user_id trigger (login|start|stop|...) notifications

        Notifications can be:

        - computed now (and registered in notifications_data)
        - fetch from the already computed (in notifications_data, and updated in notifications_data)

        Will return a dict of orders with each one being a dict of item_types with each one being a list of notifications to be shown to the user:

        notifications = {
            0: {
                "custom": [
                    {
                        "action": "custom",
                        "title": "Custom notification",
                        "footer": "Please, read this carefully",
                        "force_accept": True,
                        "notifications": [
                            {
                                "id": "0000-000",
                                "title": "Scheduled maintenance",
                                "body": "On 2025-01-01 at 00:00:00 there will be a scheduled maintenance till 2025-01-12 at 00:00:00",
                            }
                        ],
                    }
                ],
            },
            9999: {
                "desktops": [
                    {
                        "action": "last_shutdown_agent",
                        "title": "Last shutdown agent",
                        "footer": "Please, shutdown your desktops properly, world will thank you",
                        "force_accept": True,
                        "notifications": [
                            {
                                "id": "0000-000",
                                "title": "Desktop not properly shutdown",
                                "body": "Desktop [desktop_name] last time was stopped by agent [agent_name] at [date]",
                            }
                        ],
                    },
                    {
                        "action": "unused_desktops",
                        "title": "Unused desktops",
                        "footer": "Please, delete unused desktops to free resources",
                        "force_accept": False,
                        "notifications": [
                            {
                                "id": "0000-000",
                                "title": "Unused desktop",
                                "body": "Desktop [desktop_name] has been unused for 30 days and moved to recicle bin. Will be deleted in 12 days",
                            }
                        ],
                    }
                ],
                "custom": [
                    {
                        "action": "custom",
                        "title": "Custom notification",
                        "footer": "Please, read this carefully",
                        "force_accept": True,
                        "notifications": [
                            {
                                "id": "0000-000",
                                "title": "Scheduled maintenance",
                                "body": "On 2025-01-01 at 00:00:00 there will be a scheduled maintenance till 2025-01-12 at 00:00:00",
                            }
                        ],
                    }
                ],
            },
            999999: {
                "custom": [
                    {
                        "action": "custom",
                        "title": "Custom notification",
                        "footer": "Please, read this carefully",
                        "force_accept": True,
                        "notifications": [
                            {
                                "id": "0000-000",
                                "title": "Happy holidays!",
                                "body": "We wish you a merry christmas and a happy new year!",
                            }
                        ],
                    }
                ],
            },
        }

        :param payload: The payload of the request
        :type payload: dict
        :param trigger: The trigger to get the notifications for
        :type trigger: str
        :param item_type: The type of the item
        :type item_type: str
        :param item_id: The id of the item
        :type item_id: str
        :return: A dict of item_types with each one being a list of notifications_data to be shown to the user
        :rtype: dict
        """

        all_notifications = cls.get_item_notifications_by_trigger(
            trigger, True, display
        )

        notifications = []
        # Filter only the allowed notifications
        for notification in all_notifications:
            if Alloweds.is_allowed(payload, notification, "notifications", True):
                notifications.append(notification)

        user_lang = UsersProcessed.get_user_language(payload["user_id"])

        ordered_notifications = {}

        orders = sorted(set([notification["order"] for notification in notifications]))
        # For each order in the notifications retrieve the notifications for the user
        for order in orders:
            ordered_notifications[order] = {}
            for notification in notifications:
                # Check if the notification must be ignored
                if notification.get(
                    "ignore_after", datetime(1970, 1, 1, tzinfo=pytz.UTC)
                ) != datetime(1970, 1, 1, tzinfo=pytz.UTC) and notification.get(
                    "ignore_after", datetime(1970, 1, 1, tzinfo=pytz.UTC)
                ) < datetime.now().astimezone(
                    pytz.UTC
                ):
                    continue
                if notification["order"] == order:
                    # Slot per rule: item_type alone is not unique within an
                    # order (e.g. unused_desktops and
                    # unused_deployment_desktops_* all share item_type
                    # "desktop"). Key on notification id so they don't
                    # overwrite each other. Port of main 7df258e32.
                    slot_key = notification["id"]
                    ordered_notifications[order][slot_key] = {
                        "display": notification["display"],
                        "action_id": notification["action_id"],
                        "item_type": notification["item_type"],
                        "template_id": notification["template_id"],
                        "force_accept": notification["force_accept"],
                        "notifications": [],
                    }
                    if not notification.get("compute"):
                        # Get the notification template in the user language
                        notification_template_user = (
                            NotificationTemplatesProcessed.get_notification_template(
                                notification["template_id"]
                            )
                        )
                        default_lang = notification_template_user["default"]
                        lang_entries = notification_template_user.get("lang") or {}
                        fallback = (
                            notification_template_user.get("system")
                            if default_lang == "system"
                            else lang_entries.get(default_lang)
                        )
                        if fallback is None and lang_entries:
                            fallback = next(iter(lang_entries.values()))
                        notification_template_user_lang = lang_entries.get(
                            user_lang, fallback
                        )
                        ordered_notifications[order][slot_key][
                            "template"
                        ] = notification_template_user_lang
                    # If the notification is a custom notification then compute the notification
                    if notification["action_id"] == "custom":
                        # Check if the notification has already been notified
                        notifications_data = (
                            NotificationsDataProcessed.get_user_notifications_data(
                                payload["user_id"], "notified", notification["id"]
                            )
                        )
                        if notifications_data:
                            if not ordered_notifications[order][slot_key][
                                "notifications"
                            ]:
                                del ordered_notifications[order][slot_key]
                            continue
                        # Generate the notification data entry for the user
                        NotificationsDataProcessed.add_notification_data(
                            {
                                "accepted_at": None,
                                "created_at": datetime.now().astimezone(pytz.UTC),
                                "item_id": payload["user_id"],
                                "item_type": "user",
                                "notification_id": notification["id"],
                                "notified_at": datetime.now().astimezone(pytz.UTC),
                                "status": "notified",
                                "user_id": payload["user_id"],
                                "vars": {},
                                "ignore_after": notification["ignore_after"],
                            }
                        )
                        ordered_notifications[order][slot_key]["notifications"].append(
                            {
                                "id": "0000-000",
                                "vars": {
                                    "title": notification_template_user_lang["title"],
                                    "body": notification_template_user_lang["body"],
                                },
                            }
                        )
                    # If the notification is not a custom notification then fetch the notification data or compute it
                    else:
                        if notification.get("compute"):
                            # Execute the compute function
                            func = cls.computed_functions_mapping.get(
                                notification["compute"]
                            )
                            if not func:
                                log.error(
                                    f"""Notification compute function '{notification["compute"]}' not found.
                                    Please make sure it is registered in the computed_functions_mapping.
                                    Meanwhile this notification compute will be ignored."""
                                )
                                continue
                            computed_notifications = func(
                                payload, notification, user_lang
                            )
                            # Add the computed notifications to the array that object that will be returned
                            ordered_notifications[order][slot_key][
                                "notifications"
                            ] += computed_notifications
                        else:
                            notifications_data = (
                                NotificationsDataProcessed.get_user_notifications_data(
                                    payload["user_id"],
                                    "pending",
                                    notification["id"],
                                    True,
                                )
                            )
                            for notification_data in notifications_data:
                                # Format any timestamp or date variables
                                for key, value in notification_data["vars"].items():
                                    if isinstance(value, (int, float)):
                                        try:
                                            notification_data["vars"][key] = (
                                                datetime.fromtimestamp(value).strftime(
                                                    "%d/%m/%Y %H:%M"
                                                )
                                            )
                                        except ValueError:
                                            pass

                                ordered_notifications[order][slot_key][
                                    "notifications"
                                ].append(
                                    {
                                        "id": notification_data["id"],
                                        "text": __import__(
                                            "isardvdi_common.helpers.safe_format",
                                            fromlist=["safe_format"],
                                        ).safe_format(
                                            notification_template_user_lang["body"],
                                            **notification_data["vars"],
                                        ),
                                    }
                                )
                                # Update the notification data entry for the user
                                NotificationsDataProcessed.update_notification_data(
                                    {
                                        "id": notification_data["id"],
                                        "status": "notified",
                                        "notified_at": datetime.now().astimezone(
                                            pytz.UTC
                                        ),
                                    }
                                )

                    # If the notification has no notifications_data then remove it from the list
                    if not ordered_notifications[order][slot_key]["notifications"]:
                        del ordered_notifications[order][slot_key]
            # Remove the order if it is empty
            if not ordered_notifications[order]:
                del ordered_notifications[order]

        return ordered_notifications

    @classmethod
    def get_notifications_by_action_id(cls, action_id, enabled=True):
        """
        Get the notifications by action id.

        :param action_id: The action id.
        :type action_id: str
        :param enabled: Filter by enabled notifications.
        :type enabled: bool
        :return: The notifications.
        :rtype: list
        """
        query = r.table(cls._rdb_table).get_all(action_id, index="action_id")
        if enabled is not None:
            query = query.filter({"enabled": enabled})
        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    @cached(cache=notifications_cache)
    def get_all_notifications(
        cls,
    ):
        with cls._rdb_context():
            return list(
                r.table(cls._rdb_table)
                .merge(
                    lambda notification: {
                        "template": r.table(cls._rdb_table)
                        .get(notification["template_id"])
                        .default({"name": ""})
                        .pluck("name")["name"]
                    }
                )
                .run(cls._rdb_connection)
            )

    @classmethod
    def add_notification(cls, data):
        if not data.get("ignore_after"):
            data["ignore_after"] = r.epoch_time(0)
        if not data.get("keep_time"):
            data["keep_time"] = 0
        with cls._rdb_context():
            r.table(cls._rdb_table).insert(data).run(cls._rdb_connection)
        notifications_cache.clear()

    @classmethod
    def delete_notification(cls, notification_id, delete_logs=True):
        with cls._rdb_context():
            r.table(cls._rdb_table).get(notification_id).delete().run(
                cls._rdb_connection
            )
        if delete_logs:
            with cls._rdb_context():
                r.table("notifications_data").filter(
                    {"notification_id": notification_id}
                ).delete().run(cls._rdb_connection)
        notifications_cache.clear()

    @classmethod
    def get_notification(cls, notification_id):
        with cls._rdb_context():
            return r.table(cls._rdb_table).get(notification_id).run(cls._rdb_connection)

    @classmethod
    def update_notification(cls, notification_id, data):
        with cls._rdb_context():
            r.table(cls._rdb_table).get(notification_id).update(data).run(
                cls._rdb_connection
            )
        notifications_cache.clear()
