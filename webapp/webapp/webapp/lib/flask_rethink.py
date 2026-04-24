#
#   Copyright © 2023 Josep Maria Viñolas Auquer, Alberto Larraz Dalmases
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

from rethinkdb import RethinkDB

r = RethinkDB()
# ~ from ..libv1.log import *
import logging as log

from flask import current_app, g


class RDB(object):
    def __init__(self, app=None, db=None):
        self.app = app
        self.db = db
        if app is not None:
            self.init_app(app)

    def init_app(self, app):
        @app.teardown_appcontext
        def teardown(exception):
            rethinkdb = g.pop("rethinkdb", None)
            if rethinkdb is not None:
                rethinkdb.close()

    def connect(self):
        return r.connect(
            host=current_app.config["RETHINKDB_HOST"],
            port=current_app.config["RETHINKDB_PORT"],
            auth_key=current_app.config.get("RETHINKDB_AUTH"),
            db=self.db or current_app.config["RETHINKDB_DB"],
        )

    @property
    def conn(self):
        if "rethinkdb" not in g:
            g.rethinkdb = self.connect()
        return g.rethinkdb
