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

import os
import signal
import threading
from datetime import datetime, timedelta
from distutils.util import strtobool
from importlib.machinery import SourceFileLoader
from time import sleep

from api._common.api_rest import ApiRest
from api._common.storage_pool import DEFAULT_STORAGE_POOL_ID

# from api.libv2 import api_disks_watchdog
from flask import Flask
from jose import jwt

from api import app


def delete_node(*args, **kwargs):
    if hasattr(app, "storage_node_id"):
        app.logger.info(f"Deleting storage node {app.storage_node_id}")
        if not ApiRest().delete("/storage_node", json={"id": app.storage_node_id}):
            # Docker default stop timeout is 10s
            sleep(2)
            delete_node()
        else:
            app.logger.info(f"Deleted storage node {app.storage_node_id}")


def register_node():
    app.logger.info("Registering storage node")
    storage_domain = os.environ.get("STORAGE_DOMAIN", os.environ.get("DOMAIN"))
    # Haproxy is configured with 5s as health check interval
    sleep(10)
    app.storage_node_id = ApiRest().post(
        "/storage_node",
        data={
            "api_base_url": f"https://{storage_domain}/toolbox/api/check",
            "storage_pools": os.environ.get(
                "CAPABILITIES_STORAGE_POOLS", DEFAULT_STORAGE_POOL_ID
            ).split(","),
        },
    )
    if app.storage_node_id:
        app.logger.info(f"Storage node resigtered as {app.storage_node_id}")
    else:
        register_node()


if __name__ == "__main__":
    app.logger.info("Starting application")
    # api_disks_watchdog.start_disks_watchdog()
    debug = True if os.environ["LOG_LEVEL"] == "DEBUG" else False
    if strtobool(os.environ.get("CAPABILITIES_DISK", "true")):
        signal.signal(signal.SIGTERM, delete_node)
        threading.Thread(target=register_node).start()
    app.run(host="0.0.0.0", debug=debug, port=5000)
