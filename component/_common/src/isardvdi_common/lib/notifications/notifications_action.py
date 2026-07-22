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

from cachetools import cached
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
from rethinkdb import r

_get_notification_action_cache: SynchronizedTTLCache = SynchronizedTTLCache(
    maxsize=10, ttl=60
)


class NotificationsActionProcessed(RethinkSharedConnection):

    _rdb_table = "notifications_action"

    @classmethod
    @cached(cache=_get_notification_action_cache)
    def get_notification_action(cls, action_id):
        """

        Gets a notification action.

        :param action_id: The action id.
        :type action_id: str
        :return: The action.
        :rtype: dict

        """
        with cls._rdb_context():
            return r.table(cls._rdb_table).get(action_id).run(cls._rdb_connection)

    @classmethod
    def clear_get_notification_action_cache(cls):
        _get_notification_action_cache.clear()

    @classmethod
    def add_notification_action(cls, action):
        """

        Adds a notification action.

        :param action: The action.
        :type action: dict
        :return: The action.
        :rtype: dict

        """
        with cls._rdb_context():
            return r.table(cls._rdb_table).insert(action).run(cls._rdb_connection)

    @classmethod
    def get_all_notification_actions(cls):
        """

        Gets all notification actions.

        :return: The actions.
        :rtype: list

        """
        with cls._rdb_context():
            return list(r.table(cls._rdb_table).run(cls._rdb_connection))
