#
#   Copyright © 2025 Josep Maria Viñolas Auquer, Miriam Melina Gamboa Valdez
#
#   This file is part of IsardVDI.
#
#   IsardVDI is free software: you can redistribute it and/or modify
#   it under the terms of the GNU Affero General Public License as published by
#   the Free Software Foundation, either version 3 of the License, or (at your
#   option) any later version.
#
#   IsardVDI is distributed in the hope that it will be useful, but WITHOUT ANY
#   WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS
#   FOR A PARTICULAR PURPOSE. See the GNU General Public License for more
#   details.
#
#   You should have received a copy of the GNU Affero General Public License
#   along with IsardVDI. If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: AGPL-3.0-or-later

from datetime import datetime

import pytz
from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
from api.libv2.api_admin_notifications import get_notification_template
from api.libv2.api_allowed import ApiAllowed
from api.libv2.api_users import ApiUsers
from api.libv2.flask_rethink import RDB
from api.libv2.notifications.notifications_data import (
    add_notification_data,
    get_user_notifications_data,
    update_notification_data,
)

alloweds = ApiAllowed()
users = ApiUsers()


db = RDB(app)
db.init_app(app)


def get_item_notifications_by_trigger(trigger, enabled=True, display=None):
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
    query = r.table("notifications").get_all(
        [trigger, enabled], index="trigger_enabled"
    )
    if display:
        query = query.filter(
            lambda notification: notification["display"].contains(display)
        )
    with app.app_context():
        return list(query.order_by(r.desc("order")).run(db.conn))


def get_user_trigger_notifications_displays(payload, trigger):
    """
    Checks if the user has notifications for the given trigger, returns the displays.

    :param payload: The payload of the request
    :type payload: dict
    :param trigger: The trigger to get the notifications for
    :type trigger: str
    :return: A list of displays if the user has notifications for the given trigger, empty list otherwise
    :rtype: list
    """
    all_notifications = get_item_notifications_by_trigger(trigger)

    # Filter only the allowed notifications
    notifications = []
    for notification in all_notifications:
        if alloweds.is_allowed(payload, notification, "notifications", True):
            notifications.append(notification)

    displays = []
    # Check if the user has notifications for the trigger
    for notification in notifications:
        # Check if the notification must be ignored
        if notification["ignore_after"] != datetime(
            1970, 1, 1, tzinfo=pytz.UTC
        ) and notification["ignore_after"] < datetime.now().astimezone(pytz.UTC):
            continue
        if notification["action_id"] == "custom":
            notifications_data = get_user_notifications_data(
                payload["user_id"], "notified", notification["id"]
            )
            if not notifications_data:
                displays += notification["display"]
        else:
            notifications_data = get_user_notifications_data(
                payload["user_id"], "pending", notification["id"], True
            )
            if notifications_data:
                displays += notification["display"]

    return list(set(displays))


def get_user_trigger_notifications(payload, trigger, display):
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

    all_notifications = get_item_notifications_by_trigger(trigger, True, display)

    notifications = []
    # Filter only the allowed notifications
    for notification in all_notifications:
        if alloweds.is_allowed(payload, notification, "notifications", True):
            notifications.append(notification)

    user_lang = users.get_lang(payload["user_id"])

    ordered_notifications = {}

    orders = sorted(set([notification["order"] for notification in notifications]))
    # For each order in the notifications retrieve the notifications for the user
    for order in orders:
        ordered_notifications[order] = {}
        for notification in notifications:
            # Check if the notification must be ignored
            if notification["ignore_after"] != datetime(
                1970, 1, 1, tzinfo=pytz.UTC
            ) and notification["ignore_after"] < datetime.now().astimezone(pytz.UTC):
                continue
            if notification["order"] == order:
                if notification["item_type"] not in ordered_notifications[order]:
                    ordered_notifications[order][notification["item_type"]] = {}
                # Get the notification template in the user language
                notification_template_user = get_notification_template(
                    notification["template_id"]
                )
                notification_template_user_lang = notification_template_user[
                    "lang"
                ].get(
                    user_lang,
                    notification_template_user["lang"][
                        notification_template_user["default"]
                    ],
                )
                # Add the notification to the ordered_notifications
                ordered_notifications[order][notification["item_type"]] = {
                    "display": notification["display"],
                    "action_id": notification["action_id"],
                    "template_id": notification["template_id"],
                    "template": notification_template_user_lang,
                    "force_accept": notification["force_accept"],
                    "notifications": [],
                }
                # If the notification is a custom notification then compute the notification
                if notification["action_id"] == "custom":
                    # eval(notification["compute"]) TODO: Implement the compute function
                    # Check if the notification has already been notified
                    notifications_data = get_user_notifications_data(
                        payload["user_id"], "notified", notification["id"]
                    )
                    if notifications_data:
                        if not ordered_notifications[order][notification["item_type"]][
                            "notifications"
                        ]:
                            del ordered_notifications[order][notification["item_type"]]
                        continue
                    # Generate the notification data entry for the user
                    add_notification_data(
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
                    ordered_notifications[order][notification["item_type"]][
                        "notifications"
                    ].append(
                        {
                            "id": "0000-000",
                            "vars": {
                                "title": notification_template_user_lang["title"],
                                "body": notification_template_user_lang["body"],
                            },
                        }
                    )
                # If the notification is not a custom notification then fetch the notification data
                else:
                    notifications_data = get_user_notifications_data(
                        payload["user_id"], "pending", notification["id"], True
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

                        ordered_notifications[order][notification["item_type"]][
                            "notifications"
                        ].append(
                            {
                                "id": notification_data["id"],
                                "text": notification_template_user_lang["body"].format(
                                    **notification_data["vars"]
                                ),
                            }
                        )
                        # Update the notification data entry for the user
                        update_notification_data(
                            {
                                "id": notification_data["id"],
                                "status": "notified",
                                "notified_at": datetime.now().astimezone(pytz.UTC),
                            }
                        )

                # If the notification has no notifications_data then remove it from the list
                if not ordered_notifications[order][notification["item_type"]][
                    "notifications"
                ]:
                    del ordered_notifications[order][notification["item_type"]]
        # Remove the order if it is empty
        if not ordered_notifications[order]:
            del ordered_notifications[order]

    return ordered_notifications


def get_notifications_by_action_id(action_id, enabled=True):
    """
    Get the notifications by action id.

    :param action_id: The action id.
    :type action_id: str
    :param enabled: Filter by enabled notifications.
    :type enabled: bool
    :return: The notifications.
    :rtype: list
    """
    query = r.table("notifications").get_all(action_id, index="action_id")
    if enabled is not None:
        query = query.filter({"enabled": enabled})
    with app.app_context():
        return list(query.run(db.conn))
