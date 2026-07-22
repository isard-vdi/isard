#
#   Copyright © 2022 Simó Albert i Beltran
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


import logging
import os

from cachetools import cached
from isardvdi_common.connections.redis_base import RedisBase
from isardvdi_common.connections.rethink_connection_factory import (
    RethinkSharedConnection,
)
from isardvdi_common.helpers.synchronized_cache import SynchronizedTTLCache
from rethinkdb import r

_MAINTENANCE_FILE_PATH = "/usr/local/etc/isardvdi/maintenance"


class _MaintenanceMetaClass:
    def __init__(self, *arg, **kwargs):
        self._enabled = False
        self._rethink = RethinkSharedConnection()
        self._redis = RedisBase()._redis

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, enabled):
        with self._rethink._rdb_context():
            r.table("config").get(1).update({"maintenance": enabled}).run(
                self._rethink._rdb_connection
            )

        with self._redis as redis:
            redis.set("isardvdi_maintenance", str(enabled))

        self._enabled = enabled
        logging.info("Maintenance mode changed to %r.", enabled)

    @cached(SynchronizedTTLCache(maxsize=100, ttl=15))
    def category_enabled(self, category_id):
        """Check if a category is in maintenance mode"""
        with self._rethink._rdb_context():
            return (
                r.table("categories")
                .get(category_id)
                .pluck("maintenance")
                .run(self._rethink._rdb_connection)
                .get("maintenance", False)
            )

    def initialization(self):
        """Initialize maintenance mode. Check if maintenance file exists.
        If exists remove it and setting maintenance to true.
        If not exists get maintenance status form database"""
        if os.path.exists(_MAINTENANCE_FILE_PATH):
            logging.info(
                "Activating maintenance mode because the file %s is present.",
                _MAINTENANCE_FILE_PATH,
            )
            os.remove(_MAINTENANCE_FILE_PATH)
            self.enabled = True
        else:
            with self._rethink._rdb_context():
                self.enabled = (
                    r.table("config")
                    .get(1)
                    .pluck("maintenance")
                    .run(self._rethink._rdb_connection)
                    .get("maintenance", False)
                )
            logging.info("Imported maintenance mode %r from database", self.enabled)

    def get_text(self):
        with self._rethink._rdb_context():
            return (
                r.table("config")
                .get(1)["maintenance_text"]
                .run(self._rethink._rdb_connection)
            )

    def update_text(self, data):
        with self._rethink._rdb_context():
            return (
                r.table("config")
                .get(1)
                .update(
                    {"maintenance_text": {"body": data["body"], "title": data["title"]}}
                )
                .run(self._rethink._rdb_connection)
            )


class Maintenance(metaclass=_MaintenanceMetaClass):
    """Control maintenance mode status"""
