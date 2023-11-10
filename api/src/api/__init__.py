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
import shutil

from flask import Flask, render_template, send_from_directory

app = Flask(__name__, static_url_path="")

import api.libv2.log

app.url_map.strict_slashes = False

APP_ROOT = os.path.dirname(os.path.abspath(__file__))
app.STOCK_CARDS = os.path.join(APP_ROOT, "static/assets/img/desktops/stock")
if not os.path.exists(app.STOCK_CARDS):
    os.makedirs(app.STOCK_CARDS, exist_ok=True)
app.USERS_CARDS = os.path.join(APP_ROOT, "static/assets/img/desktops/user")
if not os.path.exists(app.USERS_CARDS):
    os.makedirs(app.USERS_CARDS, exist_ok=True)

# Copy only new stock images
stock_folder = os.path.join(APP_ROOT, "static/stock_assets")
for filename in os.listdir(stock_folder):
    if os.path.isfile(os.path.join(app.STOCK_CARDS, filename)):
        if (
            os.stat(os.path.join(stock_folder, filename)).st_mtime
            - os.stat(os.path.join(app.STOCK_CARDS, filename)).st_mtime
            > 1
        ):
            print("Updating stock photo: " + filename)
            shutil.copy2(
                os.path.join(stock_folder, filename),
                os.path.join(app.STOCK_CARDS, filename),
            )
    else:
        print("Adding new stock photo: " + filename)
        shutil.copy(
            os.path.join(stock_folder, filename),
            os.path.join(app.STOCK_CARDS, filename),
        )

# Max upload size
app.config["MAX_CONTENT_LENGTH"] = 1 * 1000 * 1000  # 1 MB

# '''
# App secret key for encrypting cookies
# You can generate one with:
#     import os
#     os.urandom(24)
# And paste it here.
# '''
# app.secret_key = "Change this key!//\xf7\x83\xbe\x17\xfa\xa3zT\n\\]m\xa6\x8bF\xdd\r\xf7\x9e\x1d\x1f\x14'"

from api.libv2.helpers import InternalUsers

app.internal_users = InternalUsers()

print("Starting isard api...")

from api.libv2.load_config import loadConfig

cfg = loadConfig(app)
if not cfg.init_app(app):
    exit(0)

from api.libv2.load_validator_schemas import load_validators

app.validators = load_validators()

ws_debug = True if os.environ.get("DEBUG_WEBSOCKETS", "") == "true" else False

from flask_socketio import SocketIO

# from flask_cors import CORS
# CORS(app)
# app.config["CORS_HEADERS"] = "application/json"
socketio = SocketIO(
    app,
    path="/api/v3/socket.io/",
    cors_allowed_origins="*",
    debug=ws_debug,
    logger=ws_debug,
    engineio_logger=ws_debug,
)

import logging as log

"""'
Import all views
"""
# from .views import XmlView
from .views import (
    AdminDomainsView,
    AdminDownloadsView,
    AdminResourcesView,
    AdminSchedulerView,
    AdminStoragePhysicalView,
    AdminStorageView,
    AdminTablesView,
    AdminUsageView,
    AdminUserStorage,
    AdminUsersView,
    AllowedsView,
    CardsView,
    CommonView,
    DesktopsNonPersistentView,
    DesktopsPersistentView,
    EchartsView,
    HypervisorsView,
    JumperViewerView,
    MediaViews,
    NotifyView,
    PublicView,
    QueuesView,
    RecycleBinView,
    Stats,
    StorageView,
    TemplatesView,
    UsersView,
    VpnViews,
    maintenance,
    socketio_emit,
    task,
)
from .views.bookings import BookingView, ReservablesView
from .views.deployments import DeploymentsView
