#
#   Copyright © 2022 Josep Maria Viñolas Auquer
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


import json
import logging as log
import os
import sys
import time
from pathlib import Path

from rethinkdb import RethinkDB

from scheduler import app

r = RethinkDB()


class loadConfig:
    def __init__(self, app=None):
        None

    def check_db(self):
        ready = False
        while not ready:
            try:
                conn = r.connect(
                    host=app.config["RETHINKDB_HOST"],
                    port=app.config["RETHINKDB_PORT"],
                    auth_key="",
                    db=app.config["RETHINKDB_DB"],
                )
                print("Database server OK")
                ready = True
            except Exception as e:
                # print(traceback.format_exc())
                print(
                    "Database server "
                    + app.config["RETHINKDB_HOST"]
                    + ":"
                    + app.config["RETHINKDB_PORT"]
                    + " not present. Waiting to be ready"
                )
                time.sleep(2)
        ready = False
        while not ready:
            try:
                tables = list(r.db("isard").table_list().run(conn))
            except:
                print("  No tables yet in database")
                time.sleep(1)
                continue
            if "config" in tables:
                ready = True
            else:
                print("Waiting for database to be populated with all tables...")
                print("   " + str(len(tables)) + " populated")
                time.sleep(2)

        app.ram["secrets"]["isardvdi"] = {
            "id": "isardvdi",
            "secret": os.environ["API_ISARDVDI_SECRET"],
            "description": "isardvdi",
            "domain": "localhost",
            "category_id": "default",
            "role_id": "admin",
        }
        app.secret = os.environ["API_ISARDVDI_SECRET"]

        # Load locales for QMP
        files = Path("./scheduler/locales").glob("*.json")
        app.langs = {}
        for file in files:
            f = open(file)
            app.langs[file.stem] = json.load(f).get("message-modal")

    def init_app(self, app):
        """
        Read RethinkDB configuration from environ
        """
        try:
            app.config.setdefault(
                "RETHINKDB_HOST", os.environ.get("RETHINKDB_HOST", "isard-db")
            )
            app.config.setdefault(
                "RETHINKDB_PORT", os.environ.get("RETHINKDB_PORT", "28015")
            )
            app.config.setdefault("RETHINKDB_AUTH", "")
            app.config.setdefault(
                "RETHINKDB_DB", os.environ.get("RETHINKDB_DB", "isard")
            )

            app.config.setdefault("LOG_LEVEL", os.environ.get("LOG_LEVEL", "INFO"))
            app.config.setdefault("LOG_FILE", "isard-api.log")
            app.debug = True if os.environ["LOG_LEVEL"] == "DEBUG" else False

        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            log.error(exc_type, fname, exc_tb.tb_lineno)
            log.error("Missing parameters!")
            print("Missing parameters!")
            return False
        print("Initial configuration loaded...")
        self.check_db()
        return True
