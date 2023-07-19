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
        RethinkDB, Telegram Bot, Session Cookie Name and Log Level
        """
        try:
            app.config.setdefault(
                "RETHINKDB_HOST", os.environ.get("RETHINKDB_HOST", "isard-db")
            )
            app.config.setdefault(
                "RETHINKDB_PORT", os.environ.get("RETHINKDB_PORT", "28015")
            )
            app.config.setdefault(
                "RETHINKDB_DB", os.environ.get("RETHINKDB_DB", "isard")
            )
            app.config.setdefault("url", "http://www.isardvdi.com:5050")

            app.config.setdefault("HOSTNAME", os.environ["HOSTNAME"])
            app.config.setdefault(
                "TELEGRAM_BOT_TOKEN", os.environ.get("TELEGRAM_BOT_TOKEN", False)
            )
            app.config.setdefault(
                "TELEGRAM_BOT_CHAT_ID", os.environ.get("TELEGRAM_BOT_CHAT_ID", False)
            )

            app.config["SESSION_COOKIE_NAME"] = "isard-admin"

            app.config.setdefault("LOG_LEVEL", os.environ["LOG_LEVEL"])
            app.debug = True if os.environ["LOG_LEVEL"] == "DEBUG" else False
        except Exception as e:
            print("Loading environment vars failed")
            print(e)
            exit()

        print("Initial configuration loaded from environment vars")
        print(
            "Using database connection {} and database {}".format(
                app.config["RETHINKDB_HOST"] + ":" + app.config["RETHINKDB_PORT"],
                app.config["RETHINKDB_DB"],
            )
        )

        self.wait_for_db(app)
        return True

    def wait_for_db(self, app):
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
                print("Database server not present. Waiting to be ready")
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
        sysconfig = r.db("isard").table("config").get(1).run(conn)
        app.shares_templates = sysconfig.get("shares", {}).get("templates", False)
        app.shares_isos = sysconfig.get("shares", {}).get("isos", False)
        app.wireguard_users_keys = (
            sysconfig.get("vpn_users", {}).get("wireguard", {}).get("keys", False)
        )


def load_config():
    hyper = {}
    try:
        hyper["isard-hypervisor"] = {
            "id": "isard-hypervisor",
            "hostname": "isard-hypervisor",
            "viewer_hostname": "isard-hypervisor",
            "user": "root",
            "port": "22",
            "capabilities": {"disk_operations": True, "hypervisor": True},
            "hypervisors_pools": ["default"],
            "enabled": True,
        }

        return {
            "RETHINKDB_HOST": os.environ.get("RETHINKDB_HOST", "isard-db"),
            "RETHINKDB_PORT": os.environ.get("RETHINKDB_PORT", "28015"),
            "RETHINKDB_DB": os.environ.get("RETHINKDB_DB", "isard"),
            "HOSTNAME": os.environ["HOSTNAME"],
            "TELEGRAM_BOT_TOKEN": os.environ.get("TELEGRAM_BOT_TOKEN", False),
            "TELEGRAM_BOT_CHAT_ID": os.environ.get("TELEGRAM_BOT_CHAT_ID", False),
            "LOG_LEVEL": os.environ.get("LOG_LEVEL", "INFO"),
            "url": "http://www.isardvdi.com:5050",
            #                    'LOG_FILE': rcfg.get('LOG', 'FILE'),
            "DEFAULT_HYPERVISORS": hyper,
        }
    except Exception as e:
        print("Error loading evironment variables. \n Exception: {}".format(e))
        return False
