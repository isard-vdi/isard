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

import logging as log
import os

from flask import Flask, render_template, send_from_directory

print("Starting isard scheduler...")

app = Flask(__name__, static_url_path="")
app.url_map.strict_slashes = False

# Stores data for external apps poolling in ram
app.ram = {"secrets": {}}

from scheduler.lib.load_config import loadConfig

cfg = loadConfig(app)
if not cfg.init_app(app):
    exit(0)

from flask_socketio import SocketIO

debug = True if os.environ["LOG_LEVEL"] == "DEBUG" else False
socketio = SocketIO(
    app,
    path="/api/v3/socket.io/",
    cors_allowed_origins="*",
    logger=debug,
    engineio_logger=debug,
)

"""
Scheduler
"""
from .lib.scheduler import Scheduler

log.info("Starting scheduler")
app.scheduler = Scheduler()

"""'
Import all views
"""
# from .views import XmlView
from .views import SchedulerView
