#
#   Copyright © 2025 Miriam Melina Gamboa Valdez
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

from cachetools import TTLCache, cached
from isardvdi_common.api_exceptions import Error
from rethinkdb import RethinkDB

from api import app

r = RethinkDB()
from api.libv2.flask_rethink import RDB

db = RDB(app)
db.init_app(app)


@cached(cache=TTLCache(maxsize=10, ttl=60))
def get_notification_action(action_id):
    """

    Gets a notification action.

    :param action_id: The action id.
    :type action_id: str
    :return: The action.
    :rtype: dict

    """
    with app.app_context():
        return r.table("notifications_action").get(action_id).run(db.conn)


def add_notification_action(action):
    """

    Adds a notification action.

    :param action: The action.
    :type action: dict
    :return: The action.
    :rtype: dict

    """
    with app.app_context():
        return r.table("notifications_action").insert(action).run(db.conn)
