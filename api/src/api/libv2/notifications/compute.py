from datetime import datetime

import pytz
from api.libv2.api_admin_notifications import get_notification_template_by_kind
from api.libv2.api_targets import ApiTargets
from api.libv2.api_users import get_user_last_started_desktop_log
from api.libv2.notifications.notifications_data import (
    get_user_notifications_data,
    update_notification_data,
)
from api.views.decorators import can_use_bastion

from api import app

from .notifications_data import add_notification_data

api_targets = ApiTargets()


def start_desktop_bastion(payload, notification, lang):
    """
    Calculate the bastion notifications that must be shown to the user when a desktop is started.
    """
    start_desktop_notifications = []
    bastion_notification = get_bastion_notification(payload, notification, lang)
    if bastion_notification:
        start_desktop_notifications.append(bastion_notification)

    return start_desktop_notifications


def get_bastion_notification(payload, notification, lang):
    """
    Check if the user can use bastion and if the last started desktop has bastion enabled.
    If so, return a disclaimer notification to the user.

    :param payload: The payload of the request.
    :type payload: dict
    :return: A notification to the user.
    :rtype: dict
    """
    # If the installation has bastion activated, we need to check if the lastly started desktop has bastion enabled
    bastion_allowed = can_use_bastion(payload)
    if bastion_allowed:
        # Get the last started desktop by the user
        last_desktop_log = get_user_last_started_desktop_log(payload["user_id"])

        if not last_desktop_log:
            return {}

        try:
            bastion = api_targets.get_domain_target(last_desktop_log["desktop_id"])
            if (bastion.get("http") and bastion["http"].get("enabled") is True) or (
                bastion.get("ssh") and bastion["ssh"].get("enabled") is True
            ):
                # Get the notification template in the user language
                notification_template_user = get_notification_template_by_kind(
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
                notification_data = get_user_notifications_data(
                    payload["user_id"], "notified", notification["id"]
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
                    add_notification_data(notification_data)
                # Otherwise, we need to update the notification data
                else:
                    notification_data = notification_data[0]
                    update_notification_data(
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
        except:
            return {}
    return {}


def get_not_shutdown_desktop_notification(payload, notification):
    """
    Check if the user lastly started a desktop was not shutdown by the user.
    If so, return a notification to the user reminding it to do so.

    :param payload: The payload of the request.
    :type payload: dict
    """
    # TODO: Implement this function
    # get_user_second_to_last_started_desktop function can be used to check whether the desktop was not shutdown by the user.
    # But beware that this function is not fully implemented yet.
    # It should consider the case when the user has not started any desktop yet or other cases.
    return {}
