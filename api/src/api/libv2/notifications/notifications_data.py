#
#   Copyright © 2025 Josep Maria Viñolas Auquer, Miriam Melina Gamboa Valdez, Naomi Hidalgo Piñar
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

from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
from api.libv2.flask_rethink import RDB

db = RDB(app)
db.init_app(app)


def get_user_notifications_data(
    user_id, status, notification_id, check_ignore_after=False
):
    """

    Returns the notifications data for a specific notification, user, trigger and status.

    :param user_id: The user id.
    :type user_id: str
    :param trigger: The trigger.
    :type trigger: str
    :param status: The status of the notification data.
    :type status: str
    :param notification_id: The notification id.
    :type notification_id: str
    :return: The notifications data.
    :rtype:  list

    """
    query = (
        r.table("notifications_data")
        .get_all(
            [user_id, status, notification_id],
            index="user_id_status_notification_id",
        )
        .pluck(
            "id",
            "user_id",
            "item_type",
            "template_id",
            "item_id",
            "vars",
            "status",
            "ignore_after",
        )
    )

    if check_ignore_after:
        query = query.filter(
            lambda notification_data: (
                notification_data["ignore_after"].eq(r.epoch_time(0))
                | notification_data["ignore_after"].gt(r.now())
            )
        )

    with app.app_context():
        return list(query.run(db.conn))


def add_notification_data(data):
    """
    Set the notifications data.

    :param data: The data to update.
    :type data: dict
    """
    if isinstance(data, list):
        for i in range(0, len(data), 200):
            batch_data = data[i : i + 200]
            with app.app_context():
                r.table("notifications_data").insert(batch_data).run(db.conn)
    else:
        with app.app_context():
            r.table("notifications_data").insert(data).run(db.conn)


def update_notification_data(data):
    """
    Update the notifications data.

    :param data: The data to update.
    :type data: dict
    """
    with app.app_context():
        r.table("notifications_data").get(data["id"]).update(data).run(db.conn)


def delete_users_notifications_data(users_ids):
    """
    Delete the notifications data for a list of users.

    :param users_ids: The list of users ids.
    :type users_ids: list
    """
    for i in range(0, len(users_ids), 200):
        batch_users_ids = users_ids[i : i + 200]
        with app.app_context():
            r.table("notifications_data").get_all(
                r.args(batch_users_ids), index="user_id"
            ).delete().run(db.conn)


def delete_notifications_data(notification_data_id):
    """
    Delete a notification data.

    :param notification_data_id: The notification data id.
    :type users_ids: list
    """
    with app.app_context():
        r.table("notifications_data").get(notification_data_id).delete().run(db.conn)


def delete_all_notification_data():
    """
    Delete all notification data.
    """
    with app.app_context():
        r.table("notifications_data").delete().run(db.conn)


def get_notifications_data_by_status(status, user_id):
    """
    Get all notifications data by status

    :param status: The status of the notification data (pending, notified, ...).
    :type status: str
    :param user_id: The ID of the user that received the notification.
    :type user_id: str
    :return: Notifications data.
    :rtype: list
    """
    with app.app_context():
        notifications_data = list(
            r.table("notifications_data")
            .filter({"status": status, "user_id": user_id})
            .merge(
                lambda doc: {
                    "notification_name": r.table("notifications")
                    .get(doc["notification_id"])
                    .pluck("name")["name"]
                }
            )
            .run(db.conn)
        )
    return notifications_data


def get_notifications_grouped_by_status(status):
    """
    Get all notifications data grouped by status

    :param status: The status of the notification data (pending, notified, ...).
    :type status: str
    :return: Notifications data.
    :rtype: list
    """
    with app.app_context():
        notifications_data = list(
            r.table("notifications_data")
            .filter({"status": status})
            .pluck("user_id")
            .group("user_id")
            .ungroup()
            .map(
                lambda doc: {
                    "user_id": doc["group"],
                    "user_name": r.table("users")
                    .get(doc["group"])
                    .default({"name": "[DELETED]"})["name"],
                    "notifications": doc["reduction"].count(),
                }
            )
            .run(db.conn)
        )
    return notifications_data


def get_notification_statuses():
    """
    Get all the distinct notification statuses.

    :return: All notification statuses.
    :rtype: list
    """
    with app.app_context():
        notification_statuses = list(
            r.table("notifications_data")
            .group("status")
            .ungroup()
            .map(lambda doc: doc["group"])
            .distinct()
            .run(db.conn)
        )
    return notification_statuses
