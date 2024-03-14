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

from rethinkdb import RethinkDB

from api import app

from .flask_rethink import RDB

_MAINTENANCE_FILE_PATH = "/usr/local/etc/isardvdi/maintenance"


class _MaintenanceMetaClass:
    def __init__(self, *arg, **kwargs):
        self._enabled = False
        self._rethinkdb = RethinkDB()
        self._db = RDB(app)
        self._db.init_app(app)

    @property
    def enabled(self):
        return self._enabled

    @enabled.setter
    def enabled(self, enabled):
        with app.app_context():
            self._rethinkdb.table("config").get(1).update({"maintenance": enabled}).run(
                self._db.conn
            )
        self._enabled = enabled
        logging.info("Maintenance mode changed to %r.", enabled)

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
            with app.app_context():
                self.enabled = (
                    self._rethinkdb.table("config")
                    .get(1)
                    .pluck("maintenance")
                    .run(self._db.conn)
                    .get("maintenance", False)
                )
            logging.info("Imported maintenance mode %r from database", self.enabled)

    def get_text(self):
        with app.app_context():
            return (
                self._rethinkdb.table("config")
                .get(1)["maintenance_text"]
                .run(self._db.conn)
            )

    def update_text(self, data):
        with app.app_context():
            return (
                self._rethinkdb.table("config")
                .get(1)
                .update(
                    {"maintenance_text": {"body": data["body"], "title": data["title"]}}
                )
                .run(self._db.conn)
            )

    def enable_custom_text(self, enabled):
        with app.app_context():
            return (
                self._rethinkdb.table("config")
                .get(1)
                .update({"maintenance_text": {"enabled": enabled}})
                .run(self._db.conn)
            )


class Maintenance(metaclass=_MaintenanceMetaClass):
    """Control maintenance mode status"""
