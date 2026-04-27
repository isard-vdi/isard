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
import time

from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from rethinkdb import r


class NotificationsDataProcessed(RethinkSharedConnection):

    _rdb_table = "notifications_data"

    @classmethod
    def get_user_notifications_data(
        cls, user_id, status, notification_id, check_ignore_after=False
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
            r.table(cls._rdb_table)
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

        with cls._rdb_context():
            return list(query.run(cls._rdb_connection))

    @classmethod
    def add_notification_data(cls, data):
        """
        Set the notifications data.

        :param data: The data to update.
        :type data: dict
        """
        if isinstance(data, list):
            for i in range(0, len(data), 200):
                batch_data = data[i : i + 200]
                with cls._rdb_context():
                    r.table(cls._rdb_table).insert(batch_data).run(cls._rdb_connection)
        else:
            with cls._rdb_context():
                r.table(cls._rdb_table).insert(data).run(cls._rdb_connection)

    @classmethod
    def update_notification_data(cls, data):
        """
        Update the notifications data.

        :param data: The data to update.
        :type data: dict
        """
        with cls._rdb_context():
            r.table(cls._rdb_table).get(data["id"]).update(data).run(
                cls._rdb_connection
            )

    @classmethod
    def delete_users_notifications_data(cls, users_ids):
        """
        Delete the notifications data for a list of users.

        :param users_ids: The list of users ids.
        :type users_ids: list
        """
        for i in range(0, len(users_ids), 200):
            batch_users_ids = users_ids[i : i + 200]
            with cls._rdb_context():
                r.table(cls._rdb_table).get_all(
                    r.args(batch_users_ids), index="user_id"
                ).delete().run(cls._rdb_connection)

    @classmethod
    def delete_notifications_data(cls, notification_data_id):
        """
        Delete a notification data.

        :param notification_data_id: The notification data id.
        :type users_ids: list
        """
        with cls._rdb_context():
            r.table(cls._rdb_table).get(notification_data_id).delete().run(
                cls._rdb_connection
            )

    @classmethod
    def delete_all_notification_data(cls):
        """
        Delete all notification data.
        """
        with cls._rdb_context():
            r.table(cls._rdb_table).delete().run(cls._rdb_connection)

    @classmethod
    def get_notifications_data_by_status(cls, status, user_id):
        """
        Get all notifications data by status

        :param status: The status of the notification data (pending, notified, ...).
        :type status: str
        :param user_id: The ID of the user that received the notification.
        :type user_id: str
        :return: Notifications data.
        :rtype: list
        """
        with cls._rdb_context():
            notifications_data = list(
                r.table(cls._rdb_table)
                .filter({"status": status, "user_id": user_id})
                .merge(
                    lambda doc: {
                        "notification_name": r.table("notifications")
                        .get(doc["notification_id"])
                        .pluck("name")["name"]
                    }
                )
                .run(cls._rdb_connection)
            )
        return notifications_data

    @classmethod
    def get_notifications_grouped_by_status(cls, status):
        """
        Get all notifications data grouped by status

        :param status: The status of the notification data (pending, notified, ...).
        :type status: str
        :return: Notifications data.
        :rtype: list
        """
        with cls._rdb_context():
            notifications_data = list(
                r.table(cls._rdb_table)
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
                .run(cls._rdb_connection)
            )
        return notifications_data

    @classmethod
    def get_notification_statuses(
        cls,
    ):
        """
        Get all the distinct notification statuses.

        :return: All notification statuses.
        :rtype: list
        """
        with cls._rdb_context():
            notification_statuses = list(
                r.table(cls._rdb_table)
                .group("status")
                .ungroup()
                .map(lambda doc: doc["group"])
                .distinct()
                .run(cls._rdb_connection)
            )
        return notification_statuses

    @classmethod
    def delete_expired_notifications_data(
        cls,
    ):
        """
        Delete the expired notifications data.
        """
        while True:
            log.debug("Notifications data: Deleting expired notifications data")
            with cls._rdb_context():
                expired_ids = list(
                    r.table(cls._rdb_table)
                    .eq_join("notification_id", r.table("notifications"))
                    .pluck({"left": ["id", "created_at"], "right": ["keep_time"]})
                    .zip()
                    .filter(
                        lambda row: (
                            (row["keep_time"].gt(0))
                            & (
                                (row["created_at"] + (row["keep_time"] * 3600))
                                < r.now()
                            )
                        )
                    )
                    .pluck("id")["id"]
                    .limit(500)
                    .run(cls._rdb_connection)
                )

                if not expired_ids:
                    log.debug(
                        "Notifications data: No more expired entries left to delete"
                    )
                    break  # Exit loop if no more expired entries

                # Batch delete
                r.table(cls._rdb_table).get_all(*expired_ids).delete().run(
                    cls._rdb_connection
                )

                time.sleep(1)  # Sleep for a second to avoid overloading the database
