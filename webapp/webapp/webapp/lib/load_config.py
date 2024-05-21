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

import os
import time

from rethinkdb import RethinkDB

r = RethinkDB()


class loadConfig:
    def __init__(self, app=None):
        None

    def init_app(self, app):
        """
        App configuration:
        RethinkDB, Session Cookie Name and Log Level
        """
        try:
            app.config.setdefault("url", "http://www.isardvdi.com:5050")

            app.config.setdefault("HOSTNAME", os.environ["HOSTNAME"])

            app.config["SESSION_COOKIE_NAME"] = "isard-admin"

            app.config.setdefault("LOG_LEVEL", os.environ["LOG_LEVEL"])
            app.debug = True if os.environ["LOG_LEVEL"] == "DEBUG" else False
        except Exception as e:
            print("Loading environment vars failed")
            print(e)
            exit()

        print("Initial configuration loaded from environment vars")
        return True


def load_config():
    try:
        return {
            "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO"),
        }
    except Exception as e:
        print("Error loading evironment variables. \n Exception: {}".format(e))
        return False
