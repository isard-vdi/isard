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
